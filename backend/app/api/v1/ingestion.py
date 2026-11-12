from __future__ import annotations

import hashlib
import re

from fastapi import APIRouter, Request
from sqlalchemy import select

from app import schemas as s
from app import services as svc
from app.core.security import require_writer
from app.db import (
    Application,
    Candidate,
    Confirmation,
    Event,
    IngestionJob,
    new_id,
)
from app.domain import Stage

from .common import DB, Actor, Page, PageSize, envelope, listing

router = APIRouter()


@router.get("/confirmations", response_model=s.ListResponse[s.ConfirmationRead])
def confirmations(request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20):
    return listing(
        request,
        db,
        select(Confirmation)
        .where(svc.visibility(Confirmation, actor))
        .order_by(Confirmation.created_at.desc(), Confirmation.id),
        page,
        page_size,
        s.ConfirmationRead.model_validate,
    )


@router.post("/ingestions", response_model=s.Response[s.IngestionResult])
def ingestion(request: Request, req: s.IngestionRequest, db: DB, actor: Actor):
    require_writer(actor)
    external_id = req.external_event_id or new_id()
    message_hash = hashlib.sha256(req.text.encode()).hexdigest()
    existing = db.scalar(
        select(IngestionJob).where(
            IngestionJob.source == req.source, IngestionJob.external_event_id == external_id
        )
    )
    if existing:
        if existing.actor_id != actor.id:
            svc.fail(403, "FORBIDDEN", "不能重放其他用户接入的事件")
        if existing.message_hash != message_hash:
            svc.fail(409, "IDEMPOTENCY_CONFLICT", "相同事件ID不能用于不同消息")
        previous = s.IngestionResult.model_validate(existing.extracted_json["result"])
        if previous.application_id:
            svc.get_entity(db, Application, previous.application_id, actor)
        if previous.status == "applied":
            previous.status = "duplicate"
        return envelope(request, previous)
    event_key = hashlib.sha256(f"{req.source}:{external_id}".encode()).hexdigest()
    legacy_event = db.scalar(
        select(Event).where(Event.external_event_key == event_key, Event.source == "legacy_s0")
    )
    if legacy_event and legacy_event.application_id:
        previous_application = svc.get_entity(db, Application, legacy_event.application_id, actor)
        return envelope(
            request,
            s.IngestionResult(
                status="duplicate",
                application_id=previous_application.id,
                reason="已迁移的S0历史事件，不重复执行",
            ),
        )

    def change():
        job = IngestionJob(
            actor_id=actor.id, source=req.source, external_event_id=external_id, message_hash=message_hash
        )
        db.add(job)
        result = s.IngestionResult(
            status="needs_confirmation",
            reason="仅支持明确新增或当前面试阶段的唯一编号更新；完整Parser/审核在S2实施",
        )
        creating = re.fullmatch(
            r"(?:新增|添加)([^，,\s]{1,20})[，,\s]*(?:应聘|申请)([^，,\s]{2,40})", req.text
        )
        match = re.fullmatch(
            r"(A[A-Z0-9_-]{3,39})\s*(一面通过|初试通过|二面通过|复试通过)", req.text, re.IGNORECASE
        )
        if creating:
            same_name = db.scalar(
                select(Candidate.id).where(
                    svc.visibility(Candidate, actor), Candidate.display_name == creating.group(1)
                )
            )
            if same_name:
                result.reason = "存在同名候选人，请使用候选人ID或待S2人工确认"
            else:
                obj = svc.create_application(
                    db,
                    actor,
                    s.ApplicationCreate(candidate_name=creating.group(1), position_title=creating.group(2)),
                    event_key,
                    req.source,
                )
                result = s.IngestionResult(
                    status="applied",
                    intent="create_application",
                    application_id=obj.id,
                    application=svc.application_read(obj),
                    sync_state="pending",
                )
        elif match:
            target = db.scalar(
                select(Application).where(
                    Application.application_code == match.group(1).upper(), Application.deleted_at.is_(None)
                )
            )
            if target is not None:
                svc.get_entity(db, Application, target.id, actor, write=True)
                first = match.group(2) in {"一面通过", "初试通过"}
                expected_stage = Stage.INTERVIEW_1 if first else Stage.INTERVIEW_2
                if target.stage == expected_stage:
                    changed = svc.patch_application(
                        db,
                        actor,
                        target,
                        s.ApplicationPatch(
                            stage=Stage.INTERVIEW_2 if first else Stage.OFFER,
                            change_reason="Mock明确面试阶段更新",
                        ),
                        target.version,
                        event_key,
                        req.source,
                    )
                    result = s.IngestionResult(
                        status="applied",
                        intent="update_stage",
                        application_id=target.id,
                        application=changed.application,
                        sync_state="pending",
                    )
                else:
                    result.reason = "当前阶段与消息轮次不一致，不能跳阶段或逆转"
        job.state = result.status
        job.extracted_json = {"result": result.model_dump(mode="json")}
        svc.record_change(db, job, actor, "ingest_" + result.status)
        return result

    result = svc.mutate(db, actor, "ingest:" + req.source, external_id, req.model_dump(mode="json"), change)
    return envelope(request, result)
