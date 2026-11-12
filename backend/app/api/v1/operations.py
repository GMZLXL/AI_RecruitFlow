import hashlib
import os

from fastapi import APIRouter, Request
from sqlalchemy import func, select, text

from app import schemas as s
from app.core.runtime import auth_mode, flag, gateway_path
from app.core.security import require_admin
from app.db import SCHEMA_REVISION, Notification, Outbox, WecomInbox, WorkerState, utcnow
from app.jobs.runtime import NAME
from app.services import ai_settings
from app.services.common import mutate

from .common import DB, Actor, Key, Version, envelope

router = APIRouter()


@router.get("/settings/ai", response_model=s.Response[s.AISettingsRead])
def ai_settings_read(request: Request, db: DB, actor: Actor):
    require_admin(actor)
    return envelope(request, ai_settings.metadata(db))


@router.patch("/settings/ai", response_model=s.Response[s.AISettingsRead])
def ai_settings_update(data: s.AISettingsUpdate, request: Request, db: DB, actor: Actor, expected: Version, key: Key = None):
    require_admin(actor)
    payload = {**data.model_dump(mode="json", exclude={"api_key"}), "version": expected,
        "api_key_digest": hashlib.sha256(data.api_key.get_secret_value().encode()).hexdigest() if data.api_key else None}
    return envelope(request, mutate(db, actor, "configure_ai", key, payload,
        lambda: ai_settings.save(db, actor, data, expected)))


def lease_healthy(db):
    if not flag("SYNC_WORKER_ENABLED", "true") and not flag("WECOM_WORKER_ENABLED", "true"):
        return True
    row = db.get(WorkerState, NAME)
    return bool(row and row.owner_token and row.expires_at and row.expires_at > utcnow())


@router.get("/auth/config", response_model=s.Response[s.AuthConfig])
def auth_config(request: Request):
    dev = auth_mode() == "dev"
    return envelope(request, s.AuthConfig(authentication="development_only" if dev else "sso_cookie",
        mode="hybrid" if os.getenv("APP_MODE") == "hybrid" else "mock",
        login_url=None if dev else gateway_path("SSO_LOGIN_PATH"), logout_url=None if dev else gateway_path("SSO_LOGOUT_PATH")))


@router.get("/readyz", response_model=s.Response[s.Health], responses={503: {"model": s.ErrorResponse}})
def readiness(request: Request, db: DB):
    from app.services.common import fail

    try:
        revision = db.scalar(text("SELECT version_num FROM alembic_version"))
        healthy = revision == SCHEMA_REVISION and lease_healthy(db)
    except Exception:
        healthy = False
    if not healthy:
        fail(503, "NOT_READY", "数据库迁移或后台任务未就绪")
    return envelope(request, s.Health(note="Database and configured worker lease ready"))


@router.get("/ops/status", response_model=s.Response[s.OpsStatus])
def operations_status(request: Request, db: DB, actor: Actor):
    require_admin(actor)
    lease = db.get(WorkerState, NAME)

    def counts(model):
        query = select(model.status, func.count()).group_by(model.status)
        if model is Outbox:
            query = query.where(model.entity_type == "applications")
        return {status: count for status, count in db.execute(query)}

    workers = []
    for name, setting in (("sync", "SYNC_WORKER_ENABLED"), ("wecom", "WECOM_WORKER_ENABLED")):
        row = db.get(WorkerState, name)
        workers.append(s.WorkerHealth(name="sync" if name == "sync" else "wecom", enabled=flag(setting, "true"),
            last_success_at=row.last_success_at if row else None,
            last_cycle_at=row.last_cycle_at if row else None, last_error=row.last_error if row else None))
    return envelope(request, s.OpsStatus(schema_revision=SCHEMA_REVISION or "unknown",
        worker_role=getattr(request.app.state, "worker_role", "starting"), lease_healthy=lease_healthy(db),
        heartbeat_at=lease.heartbeat_at if lease else None, workers=workers, sync_counts=counts(Outbox),
        inbox_counts=counts(WecomInbox), notification_counts=counts(Notification),
        oldest_pending_sync_at=db.scalar(select(func.min(Outbox.created_at)).where(
            Outbox.entity_type == "applications", Outbox.status.in_(["pending", "processing", "failed", "dead"]))),
        rate_limit_enabled=flag("RATE_LIMIT_ENABLED", "true")))
