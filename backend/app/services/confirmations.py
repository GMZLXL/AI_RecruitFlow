import hashlib

from sqlalchemy import select

from app import schemas as s
from app.core.errors import BusinessError
from app.db import Application, Candidate, Confirmation, IngestionJob, User, utcnow
from app.domain import ConfirmationState, Stage

from .common import (
    application_read,
    conditional_update,
    fail,
    get_entity,
    record_change,
    snapshot,
    visibility,
)
from .proposals import ReviewNeeded, apply_proposal


def confirmation_read(db, obj: Confirmation, actor: User) -> s.ConfirmationRead:
    raw = obj.proposed_json
    proposal = s.Extraction.model_validate(raw["extraction"]) if raw.get("extraction") else None
    # Recheck visibility before exposing stale candidate option snapshots.
    options = []
    for option in obj.candidates_json:
        visible = db.scalar(
            select(Application.id).where(Application.id == option["id"], visibility(Application, actor))
        )
        if visible:
            options.append(s.ApplicationRead.model_validate(option))
    job = db.get(IngestionJob, obj.ingestion_id) if obj.ingestion_id else None
    return s.ConfirmationRead(
        id=obj.id,
        version=obj.version,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        application_id=obj.application_id,
        reason=obj.reason,
        status=ConfirmationState(obj.status),
        proposal=proposal,
        candidates=options,
        message_excerpt=job.extracted_json.get("message_excerpt", "") if job else "",
        target_stage=Stage(raw["stage"]) if raw.get("stage") else None,
        expected_application_version=raw.get("expected_version"),
    )


def resolve(db, actor: User, obj: Confirmation, data: s.ResolveRequest, expected: int) -> s.ResolutionResult:
    if obj.status != "pending":
        fail(409, "CONFIRMATION_RESOLVED", "该审核任务已处理")
    if obj.version != expected:
        fail(409, "VERSION_CONFLICT", "审核任务版本已更新")
    if data.decision != "modify" and data.correction is not None:
        fail(400, "INVALID_CORRECTION", "修正字段须使用modify操作")
    if data.decision == "modify" and data.correction is None:
        fail(400, "INVALID_CORRECTION", "modify必须提供结构化修正字段")
    application = None
    if data.decision != "reject":
        raw = obj.proposed_json
        if obj.ingestion_id:
            proposal = data.correction or s.Extraction.model_validate(raw["extraction"])
        else:
            proposal = data.correction or s.Extraction(intent="update_stage", stage=Stage(raw["stage"]))
        target_id = data.application_id or obj.application_id
        if proposal.intent == "create_application":
            target_id = None
        if target_id:
            target = get_entity(db, Application, target_id, actor, write=True)
            expected_at_review = raw.get("expected_versions", {}).get(target_id, raw.get("expected_version"))
            if expected_at_review is None and data.decision == "modify":
                expected_at_review = data.expected_application_version
            if (
                data.expected_application_version is None
                or expected_at_review is None
                or data.expected_application_version != expected_at_review
                or target.version != expected_at_review
            ):
                fail(409, "VERSION_CONFLICT", "申请版本与审核快照不符，请驳回并重新录入")
        elif proposal.intent != "create_application":
            fail(400, "APPLICATION_ID_REQUIRED", "请在审核时显式选择申请")
        if data.candidate_id:
            get_entity(db, Candidate, data.candidate_id, actor, write=True)
        try:
            application = apply_proposal(
                db,
                actor,
                proposal,
                approved=True,
                selected_application=target_id,
                candidate_id=data.candidate_id,
                position_id=data.position_id,
                create_new_candidate=data.create_new_candidate,
                interview_id=data.interview_id,
                event_key=hashlib.sha256(("confirmation:" + obj.id).encode()).hexdigest(),
                source="manual_confirmation",
                manual_origin=obj.ingestion_id is None,
            )
        except ReviewNeeded as exc:
            raise BusinessError(400, exc.code, exc.message) from exc
    before = snapshot(obj)
    status = "rejected" if data.decision == "reject" else "confirmed"
    review_metadata = dict(obj.proposed_json)
    review_metadata["review_decision"] = data.decision
    review_metadata["selected_application_id"] = application.id if application else None
    if data.correction:
        review_metadata["reviewed_extraction"] = data.correction.model_dump(mode="json")
    conditional_update(
        db,
        obj,
        expected,
        {
            "status": status,
            "resolved_by": actor.id,
            "resolved_at": utcnow(),
            "proposed_json": review_metadata,
        },
    )
    record_change(db, obj, actor, "resolve_confirmation", before, data.change_reason)
    if obj.ingestion_id:
        job = db.get(IngestionJob, obj.ingestion_id)
        if job:
            previous = snapshot(job)
            result = s.IngestionResult(
                ingestion_id=job.id,
                status="failed" if status == "rejected" else "applied",
                reason_code="REJECTED_BY_REVIEWER" if status == "rejected" else None,
                application_id=application.id if application else None,
                application=application_read(application) if application else None,
                confirmation_id=obj.id,
                sync_state="pending" if application else None,
                parser_provider=job.extracted_json.get("parser", {}).get("provider", "mock"),
                mode="hybrid" if job.extracted_json.get("result", {}).get("mode") == "hybrid" else "mock",
            )
            metadata = dict(job.extracted_json)
            metadata["result"] = result.model_dump(mode="json")
            conditional_update(db, job, job.version, {"state": result.status, "extracted_json": metadata})
            record_change(db, job, actor, "resolve_ingestion", previous, data.change_reason)
    return s.ResolutionResult(
        confirmation_id=obj.id,
        status=status,
        version=obj.version,
        application=application_read(application) if application else None,
    )
