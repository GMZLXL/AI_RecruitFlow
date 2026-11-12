from __future__ import annotations

import os

from fastapi import APIRouter, Request
from sqlalchemy import select

from app import schemas as s
from app.core.security import DEV_IDS, require_admin
from app.db import (
    User,
)

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
    return envelope(request, s.Identity(user=s.UserRead.model_validate(actor)))


@router.get("/dev/users", response_model=s.Response[list[s.UserRead]])
def development_users(request: Request, db: DB, actor: Actor):
    users = db.scalars(select(User).where(User.id.in_(DEV_IDS.values()), User.active.is_(True))).all()
    return envelope(request, [s.UserRead.model_validate(user) for user in users])


@router.get("/integrations/status", response_model=s.Response[s.IntegrationStatus])
def integration_status(request: Request, actor: Actor):
    require_admin(actor)
    data = s.IntegrationStatus(mode="hybrid" if os.getenv("APP_MODE") == "hybrid" else "mock")
    if os.getenv("AI_PROVIDER", "mock") == "deepseek":
        data.parser_provider = "deepseek"
        data.model = os.getenv("DEEPSEEK_MODEL") or None
        data.deepseek = (
            "mode_mismatch"
            if data.mode == "mock"
            else "configured_not_verified"
            if os.getenv("DEEPSEEK_API_KEY")
            else "blocked_by_credentials"
        )
    return envelope(request, data)
