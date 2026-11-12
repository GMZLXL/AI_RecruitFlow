from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from app import schemas as s
from app import services as svc
from app.core.security import require_admin
from app.db import (
    AuditLog,
    Outbox,
    RemoteLink,
    new_id,
)

from .common import DB, Actor, Key, Page, PageSize, envelope, listing

router = APIRouter()


@router.get("/sync/jobs", response_model=s.ListResponse[s.SyncJob])
def sync_jobs(request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20):
    require_admin(actor)
    return listing(
        request,
        db,
        select(Outbox).order_by(Outbox.created_at.desc(), Outbox.id),
        page,
        page_size,
        s.SyncJob.model_validate,
    )


@router.post("/sync/run", response_model=s.Response[s.SyncRun])
def run_mock_sync(request: Request, db: DB, actor: Actor, key: Key = None):
    require_admin(actor)

    def change():
        jobs = db.scalars(
            select(Outbox).where(Outbox.status == "pending").order_by(Outbox.created_at, Outbox.id)
        ).all()
        for job in jobs:
            if job.entity_type == "applications":
                link = db.scalar(
                    select(RemoteLink).where(
                        RemoteLink.entity_type == job.entity_type,
                        RemoteLink.entity_id == job.entity_id,
                        RemoteLink.provider == "mock",
                    )
                )
                if link is None:
                    link = RemoteLink(
                        entity_type=job.entity_type,
                        entity_id=job.entity_id,
                        application_id=job.application_id,
                        remote_record_id="MOCK-" + new_id()[:8],
                        provider="mock",
                        last_synced_version=0,
                    )
                    db.add(link)
                    db.flush()
                link.last_synced_version = max(link.last_synced_version, job.version)
                job.remote_record_id = link.remote_record_id
            job.status = "mock_synced"
            job.attempts += 1
            db.add(
                AuditLog(
                    actor_id=actor.id,
                    action="mock_sync",
                    target_type="sync_outbox",
                    target_id=job.id,
                    metadata_json={
                        "version": job.version,
                        "mode": "mock",
                        "internal_only": job.entity_type != "applications",
                    },
                )
            )
        return s.SyncRun(processed=len(jobs))

    return envelope(request, svc.mutate(db, actor, "run_mock_sync", key, {}, change))
