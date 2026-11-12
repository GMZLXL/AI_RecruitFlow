from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app import schemas as s
from app.core.security import require_admin
from app.db import AuditLog, Outbox, new_id
from app.domain import SyncState
from app.integrations.smartsheet.factory import sync_provider
from app.integrations.smartsheet.tencent import tencent_status
from app.jobs.sync_worker import worker_enabled
from app.services.common import mutate
from app.services.sync import retry, sync_job

from .common import DB, Actor, Key, Page, PageSize, Version, envelope, listing

router = APIRouter()


@router.get("/sync/jobs", response_model=s.ListResponse[s.SyncJob])
def sync_jobs(
    request: Request,
    db: DB,
    actor: Actor,
    page: Page = 1,
    page_size: PageSize = 20,
    status: SyncState | None = None,
    application_id: Annotated[str | None, Query(max_length=36)] = None,
):
    require_admin(actor)
    query = select(Outbox)
    if status:
        query = query.where(Outbox.status == status.value)
    if application_id:
        query = query.where(Outbox.application_id == application_id)
    return listing(
        request,
        db,
        query.order_by(Outbox.created_at.desc(), Outbox.version.desc(), Outbox.id),
        page,
        page_size,
        sync_job,
    )


@router.get("/sync/summary", response_model=s.Response[s.SyncSummary])
def sync_summary(request: Request, db: DB, actor: Actor):
    require_admin(actor)
    counts = {
        SyncState(status): count
        for status, count in db.execute(select(Outbox.status, func.count(Outbox.id)).group_by(Outbox.status))
    }
    last = db.scalar(
        select(func.max(Outbox.completed_at)).where(
            Outbox.entity_type == "applications", Outbox.status.in_(["mock_synced", "synced"])
        )
    )
    return envelope(
        request,
        s.SyncSummary(
            counts=counts,
            last_success_at=last,
            worker_enabled=worker_enabled(),
            provider=sync_provider(),
            tencent_docs=tencent_status(),
            message="Mock任务仅写本机模拟表；腾讯文档尚未通过授权和工具Schema验证",
        ),
    )


@router.post("/sync/run", response_model=s.Response[s.SyncRun], status_code=202)
async def run_mock_sync(request: Request, db: DB, actor: Actor, key: Key = None):
    require_admin(actor)

    def change():
        db.add(
            AuditLog(
                actor_id=actor.id,
                action="request_sync_run",
                target_type="sync_worker",
                target_id=new_id(),
                metadata_json={"accepted": True},
            )
        )
        return s.SyncRun()

    result = mutate(db, actor, "request_sync_run", key, {}, change)
    db.close()
    request.app.state.sync_wakeup.set()
    return envelope(request, result)


@router.post("/sync/jobs/{job_id}/retry", response_model=s.Response[s.SyncJob])
async def retry_sync(
    request: Request, job_id: str, req: s.SyncRetry, db: DB, actor: Actor, expected: Version, key: Key = None
):
    require_admin(actor)
    result = mutate(
        db,
        actor,
        "retry_sync:" + job_id,
        key,
        {**req.model_dump(), "revision": expected},
        lambda: retry(db, actor, job_id, expected, req.reason),
    )
    db.close()
    request.app.state.sync_wakeup.set()
    return envelope(request, result)
