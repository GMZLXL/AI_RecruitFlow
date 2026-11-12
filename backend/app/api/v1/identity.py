from __future__ import annotations

import os

from fastapi import APIRouter, Request
from sqlalchemy import select

from app import schemas as s
from app.core.runtime import auth_mode
from app.core.security import DEV_IDS, dev_auth_enabled, require_admin
from app.db import (
    User,
)
from app.integrations.smartsheet.factory import sync_provider
from app.integrations.smartsheet.tencent import tencent_status
from app.integrations.wecom.config import status as wecom_status

from .common import DB, Actor, envelope

router = APIRouter()


@router.get("/health", response_model=s.Response[s.Health])
def health(request: Request):
    return envelope(request, s.Health(mode="hybrid" if os.getenv("APP_MODE") == "hybrid" else "mock"))


@router.get("/ready", response_model=s.Response[s.Health])
def ready(request: Request, db: DB, actor: Actor):
    db.execute(select(1))
    return envelope(request, s.Health(note="Database schema and connection ready"))


@router.get("/me", response_model=s.Response[s.Identity])
def me(request: Request, actor: Actor):
    return envelope(request, s.Identity(user=s.UserRead.model_validate(actor),
        mode="hybrid" if os.getenv("APP_MODE") == "hybrid" else "mock",
        authentication="sso_cookie" if auth_mode() == "sso" else "development_only",
        csrf_token=getattr(request.state, "csrf_token", None)))


@router.get("/dev/users", response_model=s.Response[list[s.UserRead]])
def development_users(request: Request, db: DB, actor: Actor):
    if not dev_auth_enabled():
        from app.services.common import fail

        fail(403, "DEV_IDENTITY_FORBIDDEN", "当前认证模式不提供模拟用户目录")
    users = db.scalars(select(User).where(User.id.in_(DEV_IDS.values()), User.active.is_(True))).all()
    return envelope(request, [s.UserRead.model_validate(user) for user in users])


@router.get("/integrations/status", response_model=s.Response[s.IntegrationStatus])
def integration_status(request: Request, actor: Actor):
    require_admin(actor)
    data = s.IntegrationStatus(mode="hybrid" if os.getenv("APP_MODE") == "hybrid" else "mock",
                               sync_provider=sync_provider(), tencent_docs=tencent_status(), wecom=wecom_status().callback)
    from app.db import SessionLocal
    from app.services.ai_settings import metadata

    with SessionLocal() as db:
        ai = metadata(db)
    if ai.provider == "deepseek":
        data.parser_provider = "deepseek"
        data.model = ai.model or None
        data.deepseek = (
            "mode_mismatch"
            if data.mode == "mock"
            else "configured_not_verified"
            if ai.has_api_key
            else "blocked_by_credentials"
        )
    return envelope(request, data)
