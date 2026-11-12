"""Durable claim -> parser outside all DB transactions -> controlled atomic application."""

import hashlib
import os
import re
from dataclasses import asdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import schemas as s
from app.core.security import require_writer
from app.db import Application, Confirmation, Event, IngestionJob, SessionLocal, User, new_id, utcnow
from app.integrations.parsers.base import ParseOutcome, Parser
from app.integrations.parsers.privacy import redact

from .common import application_read, conditional_update, fail, get_entity, record_change, snapshot
from .proposals import ReviewNeeded, apply_proposal


def active_actor(db, actor_id):
    actor = db.get(User, actor_id)
    if actor is None or not actor.active or actor.deleted_at is not None:
        fail(403, "FORBIDDEN", "处理期间用户权限已失效")
    require_writer(actor)
    return actor


def result_for_job(job: IngestionJob) -> s.IngestionResult:
    raw = job.extracted_json.get("result")
    if raw:
        result = s.IngestionResult.model_validate(raw)
        result.ingestion_id = job.id
        if result.status == "applied":
            result.status = "duplicate"
        return result
    return s.IngestionResult(ingestion_id=job.id, status="parsing", reason="事件正在处理中")


def claim(actor_id: str, req: s.IngestionRequest, reference_time=None):
    external_id = req.external_event_id or new_id()
    digest = hashlib.sha256(req.text.encode()).hexdigest()
    with SessionLocal() as db:
        actor = active_actor(db, actor_id)
        job = db.scalar(
            select(IngestionJob).where(
                IngestionJob.source == req.source, IngestionJob.external_event_id == external_id
            )
        )
        if job:
            if job.actor_id != actor_id:
                fail(403, "FORBIDDEN", "不能重放其他用户接入的事件")
            if (
                job.message_hash != digest
                or job.extracted_json.get("execute_if_unambiguous", True) != req.execute_if_unambiguous
            ):
                fail(409, "IDEMPOTENCY_CONFLICT", "相同事件ID不能用于不同消息或执行选项")
            legacy_review = job.state == "needs_confirmation" and not job.extracted_json.get(
                "result", {}
            ).get("confirmation_id")
            if job.state not in {"received", "parsing"} and not legacy_review:
                result = result_for_job(job)
                if result.application_id:
                    get_entity(db, Application, result.application_id, actor)
                return result
            if job.processing_started_at and job.processing_started_at > utcnow() - timedelta(seconds=120):
                return result_for_job(job)
        else:
            event_key = hashlib.sha256(f"{req.source}:{external_id}".encode()).hexdigest()
            legacy = db.scalar(
                select(Event).where(Event.external_event_key == event_key, Event.source == "legacy_s0")
            )
            if legacy and legacy.application_id:
                application = get_entity(db, Application, legacy.application_id, actor)
                return s.IngestionResult(
                    status="duplicate", application_id=application.id, reason="已迁移历史事件"
                )
        token = new_id()
        if job:
            before = snapshot(job)
            conditional_update(
                db,
                job,
                job.version,
                {"state": "parsing", "processing_token": token, "processing_started_at": utcnow()},
            )
            record_change(db, job, actor, "resume_ingestion", before)
        else:
            job = IngestionJob(
                received_at=reference_time or utcnow(),
                actor_id=actor_id,
                source=req.source,
                external_event_id=external_id,
                message_hash=digest,
                state="parsing",
                processing_token=token,
                processing_started_at=utcnow(),
                extracted_json={
                    "message_excerpt": redact(req.text)[:300],
                    "execute_if_unambiguous": req.execute_if_unambiguous,
                },
            )
            db.add(job)
            record_change(db, job, actor, "receive_ingestion")
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            fail(409, "EVENT_IN_PROGRESS", "相同事件已被接收，请使用原事件ID重试")
        return job.id, token, job.version, job.received_at


def claimed_job(db, job_id, token, version):
    job = db.get(IngestionJob, job_id)
    if job is None or job.state != "parsing" or job.processing_token != token or job.version != version:
        fail(409, "INGESTION_SUPERSEDED", "事件处理租约已变更，请查询最新结果")
    return job


def complete_job(db, job, actor, outcome: ParseOutcome, result: s.IngestionResult):
    before = snapshot(job)
    metadata = dict(job.extracted_json)
    parsed = asdict(outcome)
    parsed.pop("extraction", None)
    metadata.update(
        {
            "extraction": outcome.extraction.model_dump(mode="json"),
            "parser": parsed,
            "result": result.model_dump(mode="json"),
        }
    )
    conditional_update(
        db,
        job,
        job.version,
        {
            "state": result.status,
            "error_code": outcome.error_code,
            "extracted_json": metadata,
            "processing_token": None,
            "processing_started_at": None,
        },
    )
    record_change(db, job, actor, "finish_ingestion", before)


async def ingest(actor_id: str, req: s.IngestionRequest, parser: Parser, *, reference_time=None) -> s.IngestionResult:
    try:
        received = claim(actor_id, req, reference_time)
    except IntegrityError:
        received = claim(actor_id, req, reference_time)  # the other claim committed its unique event first
    if isinstance(received, s.IngestionResult):
        return received
    job_id, token, version, reference_time = received
    try:
        safe_text = redact(req.text)
        codes = {
            code.upper()
            for code in re.findall(r"(?<![A-Za-z0-9_])A[A-Z0-9_-]{3,39}(?![A-Za-z0-9_])", safe_text, re.I)
        }
        results = re.findall(r"(?:一面|初试|二面|复试)(?:未通过|不通过|通过|过了)", safe_text)
        conflict = (
            "MULTIPLE_APPLICATIONS" if len(codes) > 1 else "MULTIPLE_RESULTS" if len(results) > 1 else None
        )
        if conflict:
            outcome = ParseOutcome(
                s.Extraction(intent="unknown", should_confirm=True, ambiguities=[conflict]),
                provider=getattr(parser, "provider", "mock"),
                error_code=conflict,
                attempts=0,
            )
        else:
            outcome = await parser.parse(
                safe_text, reference_time, os.getenv("APP_TIMEZONE", "Asia/Shanghai")
            )
    except Exception:
        outcome = ParseOutcome(error_code="PARSER_FAILURE", provider=getattr(parser, "provider", "mock"))
    review = None
    try:
        with SessionLocal() as db:
            actor = active_actor(db, actor_id)
            job = claimed_job(db, job_id, token, version)
            if outcome.error_code:
                raise ReviewNeeded(outcome.error_code, "解析未完成，需人工审核或修正")
            if not req.execute_if_unambiguous:
                from .proposals import matches

                options = [
                    application_read(a).model_dump(mode="json")
                    for a in matches(db, actor, outcome.extraction)
                ]
                raise ReviewNeeded("REVIEW_REQUESTED", "用户选择先审核再执行", options)
            application = apply_proposal(
                db,
                actor,
                outcome.extraction,
                event_key=hashlib.sha256(f"{req.source}:{job.external_event_id}".encode()).hexdigest(),
                source=req.source,
            )
            result = s.IngestionResult(
                ingestion_id=job.id,
                status="applied",
                intent=outcome.extraction.intent,
                application_id=application.id,
                application=application_read(application),
                sync_state="pending",
                parser_provider=outcome.provider,
                mode="hybrid" if os.getenv("APP_MODE") == "hybrid" else "mock",
            )
            complete_job(db, job, actor, outcome, result)
            db.commit()
            return result
    except ReviewNeeded as exc:
        review = exc
    except Exception as exc:
        from app.core.errors import BusinessError

        if not isinstance(exc, BusinessError) or exc.status in {401, 403}:
            raise
        review = ReviewNeeded(exc.code, exc.message)
    # The failed application transaction was rolled back by closing its session.
    # No partial interview/application writes survive when a compound message needs review.
    with SessionLocal() as db:
        actor = active_actor(db, actor_id)
        job = claimed_job(db, job_id, token, version)
        options = review.candidates
        if not options:
            from .proposals import matches

            options = [
                application_read(a).model_dump(mode="json") for a in matches(db, actor, outcome.extraction)
            ]
        confirmation = Confirmation(
            ingestion_id=job.id,
            owner_id=actor.id,
            application_id=options[0]["id"] if len(options) == 1 else None,
            reason=review.code,
            candidates_json=options,
            proposed_json={
                "extraction": outcome.extraction.model_dump(mode="json"),
                "candidate_ids": review.candidate_ids,
                "expected_versions": {a["id"]: a["version"] for a in options},
            },
        )
        db.add(confirmation)
        record_change(db, confirmation, actor, "request_confirmation")
        result = s.IngestionResult(
            ingestion_id=job.id,
            status="needs_confirmation",
            intent=outcome.extraction.intent,
            reason=review.message,
            reason_code=review.code,
            confirmation_id=confirmation.id,
            parser_provider=outcome.provider,
            mode="hybrid" if os.getenv("APP_MODE") == "hybrid" else "mock",
        )
        complete_job(db, job, actor, outcome, result)
        db.commit()
        return result
