"""Short durable claim, no open transaction during remote IO, fenced acknowledgement."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import or_, select, update

from app import schemas as s
from app.core.security import SYNC_ACTOR_ID
from app.db import (
    Application,
    AuditLog,
    Candidate,
    Outbox,
    Position,
    RemoteLink,
    SessionLocal,
    SyncWorkerLease,
    new_id,
    utcnow,
)
from app.domain import Outcome, Stage, SyncState
from app.integrations.smartsheet.base import SheetError
from app.integrations.smartsheet.factory import sheet_adapter

from .common import fail, redact_reason

LEASE_SECONDS = 120
REMOTE_TIMEOUT_SECONDS = 20
MAX_ATTEMPTS = 5
RETRY_BASE_SECONDS = 5
RETRY_CAP_SECONDS = 300
ERROR_CODES = {
    "REMOTE_TIMEOUT",
    "REMOTE_UNAVAILABLE",
    "REMOTE_PERMISSION_DENIED",
    "REMOTE_RECORD_MISSING",
    "REMOTE_MAPPING_MISSING",
    "BLOCKED_BY_CREDENTIALS",
    "BLOCKED_BY_SCHEMA",
    "INVALID_PROJECTION",
    "REMOTE_ID_INVALID",
    "INTERNAL_SYNC_ERROR",
    "CLAIM_EXPIRED",
}


def audit(db, job, action, metadata):
    db.add(
        AuditLog(
            actor_id=SYNC_ACTOR_ID,
            action=action,
            target_type="sync_outbox",
            target_id=job.id,
            metadata_json={"automated": True, "provider": job.provider, **metadata},
        )
    )


def safe_error(code: str | None) -> str | None:
    return code if code in ERROR_CODES or code is None else "LEGACY_SYNC_ERROR"


def sync_job(job: Outbox) -> s.SyncJob:
    return s.SyncJob(
        id=job.id,
        entity_type=job.entity_type,
        entity_id=job.entity_id,
        application_id=job.application_id,
        version=job.version,
        status=SyncState(job.status),
        remote_record_id=job.remote_record_id,
        attempts=job.attempts,
        cycle_attempts=job.cycle_attempts,
        provider="mock" if job.provider == "mock" else "tencent_docs",
        mode="mock" if job.provider == "mock" else "real",
        revision=job.revision,
        internal_only=job.entity_type != "applications",
        last_error=safe_error(job.last_error)
        if job.status in {"pending", "processing", "failed", "dead"}
        else None,
        next_retry_at=job.next_retry_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )


def retry(db, actor, job_id: str, expected: int, reason: str) -> s.SyncJob:
    job = db.get(Outbox, job_id)
    if job is None:
        fail(404, "NOT_FOUND", "同步任务不存在")
    if job.revision != expected:
        fail(409, "VERSION_CONFLICT", "任务状态已更新，请刷新")
    if job.status not in {"failed", "dead"}:
        fail(409, "INVALID_SYNC_STATE", "仅失败或死信任务可以重试")
    if not reason.strip():
        fail(422, "INVALID_REASON", "重试说明不能为空")
    changed = db.execute(
        update(Outbox)
        .where(
            Outbox.id == job_id,
            Outbox.revision == expected,
            Outbox.status.in_(["failed", "dead"]),
        )
        .values(
            status="pending",
            revision=expected + 1,
            cycle_attempts=0,
            next_retry_at=None,
            completed_at=None,
            processing_token=None,
            lease_expires_at=None,
        )
        .returning(Outbox.id)
    ).scalar_one_or_none()
    if changed is None:
        fail(409, "VERSION_CONFLICT", "任务状态已更新，请刷新")
    db.refresh(job)
    db.add(
        AuditLog(
            actor_id=actor.id,
            action="retry_sync",
            target_type="sync_outbox",
            target_id=job.id,
            metadata_json={
                "reason": redact_reason(reason),
                "revision": job.revision,
                "previous_error": safe_error(job.last_error),
            },
        )
    )
    return sync_job(job)


def acquire(now: datetime) -> str | None:
    token = new_id()
    with SessionLocal() as db:
        # Rows are seeded by migration; tests that clear all tables may recreate an empty lease.
        if db.get(SyncWorkerLease, "smartsheet") is None:
            from sqlalchemy.dialects.postgresql import insert as postgres_insert
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            insert = (
                sqlite_insert if db.bind is not None and db.bind.dialect.name == "sqlite" else postgres_insert
            )
            db.execute(insert(SyncWorkerLease).values(name="smartsheet").on_conflict_do_nothing())
        taken = db.execute(
            update(SyncWorkerLease)
            .where(
                SyncWorkerLease.name == "smartsheet",
                or_(SyncWorkerLease.token.is_(None), SyncWorkerLease.expires_at <= now),
            )
            .values(token=token, expires_at=now + timedelta(seconds=LEASE_SECONDS))
            .returning(SyncWorkerLease.name)
        ).scalar_one_or_none()
        db.commit()
        return token if taken else None


def projection(db, job: Outbox) -> s.ApplicationProjection:
    payload = job.payload_json
    if payload.get("schema_version") != 1:
        raise SheetError("INVALID_PROJECTION")
    if "projection" in payload:
        result = s.ApplicationProjection.model_validate(payload["projection"])
    else:
        # S1/S2 compatibility: retain the immutable version/stage, resolve legacy display labels.
        entity = payload["entity"]
        application = db.get(Application, job.entity_id)
        if not application:
            raise SheetError("INVALID_PROJECTION")
        candidate = db.get(Candidate, entity["candidate_id"])
        position = db.get(Position, entity["position_id"])
        if not candidate or not position:
            raise SheetError("INVALID_PROJECTION")
        result = s.ApplicationProjection(
            application_id=job.entity_id,
            application_code=entity["application_code"],
            candidate_name=candidate.display_name,
            position_title=position.title,
            stage=Stage(entity["stage"]),
            outcome=Outcome(entity["outcome"]),
            version=job.version,
            deleted=bool(entity.get("deleted_at")),
            updated_at=entity["updated_at"],
        )
    if result.application_id != job.entity_id or result.version != job.version:
        raise SheetError("INVALID_PROJECTION")
    return result


@dataclass(frozen=True)
class Claim:
    id: str
    token: str
    provider: str
    remote_id: str | None
    projection: s.ApplicationProjection


def claim_next(worker_token: str, now: datetime) -> tuple[Claim | None, bool]:
    with SessionLocal() as db:
        lease = db.execute(
            update(SyncWorkerLease)
            .where(
                SyncWorkerLease.name == "smartsheet",
                SyncWorkerLease.token == worker_token,
                SyncWorkerLease.expires_at > now,
            )
            .values(expires_at=now + timedelta(seconds=LEASE_SECONDS))
            .returning(SyncWorkerLease.name)
        ).scalar_one_or_none()
        if not lease:
            return None, False
        job = db.scalar(
            select(Outbox)
            .where(
                or_(
                    Outbox.status == "pending",
                    (Outbox.status == "failed") & (Outbox.next_retry_at <= now),
                    (Outbox.status == "processing") & (Outbox.lease_expires_at <= now),
                )
            )
            .order_by(Outbox.created_at, Outbox.version, Outbox.id)
            .limit(1)
        )
        if job is None:
            db.commit()
            return None, False
        if job.cycle_attempts >= MAX_ATTEMPTS:
            job.status, job.last_error = "dead", "CLAIM_EXPIRED"
            job.next_retry_at = None
            job.revision += 1
            job.processing_token = job.lease_expires_at = None
            audit(db, job, "sync_dead", {"error": job.last_error})
            db.commit()
            return None, True
        if job.entity_type != "applications":
            job.status = "mock_synced" if job.provider == "mock" else "synced"
            job.completed_at, job.next_retry_at = now, None
            job.revision += 1
            audit(db, job, "sync_internal", {"internal_only": True})
            db.commit()
            return None, True
        link = db.scalar(
            select(RemoteLink).where(
                RemoteLink.entity_type == "applications",
                RemoteLink.entity_id == job.entity_id,
                RemoteLink.provider == job.provider,
            )
        )
        if link and link.last_synced_version >= job.version:
            job.status, job.remote_record_id = "superseded", link.remote_record_id
            job.completed_at, job.next_retry_at = now, None
            job.last_error = None
            job.processing_token = job.lease_expires_at = None
            job.revision += 1
            audit(db, job, "sync_superseded", {"remote_version": link.last_synced_version})
            db.commit()
            return None, True
        token = new_id()
        job.status, job.processing_token = "processing", token
        job.next_retry_at = None
        job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        job.attempts += 1
        job.cycle_attempts += 1
        job.revision += 1
        try:
            if link is None and db.scalar(
                select(Outbox.id)
                .where(
                    Outbox.entity_id == job.entity_id,
                    Outbox.entity_type == "applications",
                    Outbox.provider == job.provider,
                    Outbox.remote_record_id.is_not(None),
                )
                .limit(1)
            ):
                raise SheetError("REMOTE_MAPPING_MISSING")
            data = projection(db, job)
        except (KeyError, ValueError, ValidationError, SheetError) as exc:
            job.status = "dead"
            job.last_error = exc.code if isinstance(exc, SheetError) else "INVALID_PROJECTION"
            job.processing_token = job.lease_expires_at = None
            audit(db, job, "sync_dead", {"error": job.last_error})
            db.commit()
            return None, True
        audit(db, job, "sync_claim", {"attempt": job.attempts, "version": job.version})
        result = Claim(job.id, token, job.provider, link.remote_record_id if link else None, data)
        db.commit()
        return result, True


def acknowledge(claim: Claim, remote_id: str | None, error: SheetError | None, now: datetime):
    with SessionLocal() as db:
        owned = db.execute(
            update(Outbox)
            .where(
                Outbox.id == claim.id,
                Outbox.status == "processing",
                Outbox.processing_token == claim.token,
            )
            .values(revision=Outbox.revision + 1)
            .returning(Outbox.id)
        ).scalar_one_or_none()
        if owned is None:
            return  # A recovered worker owns the task; stale results cannot change local state.
        job = db.get(Outbox, claim.id)
        assert job is not None
        if error:
            job.last_error = error.code if error.code in ERROR_CODES else "INTERNAL_SYNC_ERROR"
            job.status = "failed" if error.retryable and job.cycle_attempts < MAX_ATTEMPTS else "dead"
            job.next_retry_at = (
                now
                + timedelta(
                    seconds=min(RETRY_CAP_SECONDS, RETRY_BASE_SECONDS * 2 ** (job.cycle_attempts - 1))
                )
                if job.status == "failed"
                else None
            )
            audit(db, job, "sync_" + job.status, {"error": job.last_error, "attempt": job.attempts})
        else:
            link = db.scalar(
                select(RemoteLink).where(
                    RemoteLink.entity_type == "applications",
                    RemoteLink.entity_id == job.entity_id,
                    RemoteLink.provider == job.provider,
                )
            )
            if link is None:
                link = RemoteLink(
                    entity_type="applications",
                    entity_id=job.entity_id,
                    application_id=job.application_id,
                    provider=job.provider,
                    remote_record_id=remote_id,
                    last_synced_version=0,
                )
                db.add(link)
            link.last_synced_version = max(link.last_synced_version, job.version)
            job.remote_record_id, job.completed_at = remote_id, now
            job.status = "mock_synced" if job.provider == "mock" else "synced"
            job.last_error = job.next_retry_at = None
            audit(
                db,
                job,
                "sync_success",
                {"mode": "mock" if job.provider == "mock" else "real", "version": job.version},
            )
        job.processing_token = job.lease_expires_at = None
        db.commit()


async def process_batch(limit: int = 50, *, now: datetime | None = None) -> int:
    token = acquire(now or utcnow())
    if token is None:
        return 0
    processed = 0
    try:
        for _ in range(min(max(limit, 1), 100)):
            claim, found = claim_next(token, now or utcnow())
            if not found:
                break
            processed += 1
            if claim is None:
                continue
            error, remote_id = None, None
            try:
                remote_id = await asyncio.wait_for(
                    sheet_adapter(claim.provider).upsert_application(claim.projection, claim.remote_id),
                    timeout=REMOTE_TIMEOUT_SECONDS,
                )
                if (
                    not remote_id
                    or len(remote_id) > 100
                    or not remote_id.isascii()
                    or any(c.isspace() for c in remote_id)
                ):
                    raise SheetError("REMOTE_ID_INVALID")
            except TimeoutError:
                error = SheetError("REMOTE_TIMEOUT", retryable=True)
            except SheetError as exc:
                error = exc
            except Exception:
                error = SheetError("INTERNAL_SYNC_ERROR")
            acknowledge(claim, remote_id, error, now or utcnow())
    finally:
        with SessionLocal() as db:
            db.execute(
                update(SyncWorkerLease)
                .where(SyncWorkerLease.name == "smartsheet", SyncWorkerLease.token == token)
                .values(token=None, expires_at=None)
            )
            db.commit()
    return processed
