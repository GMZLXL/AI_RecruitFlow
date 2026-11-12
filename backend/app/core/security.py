import os
import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessError
from app.db import SessionLocal, User, get_db
from app.domain import Role

DEV_DIRECTORY = {
    "admin": ("模拟管理员", Role.ADMIN, "engineering"),
    "hr-a": ("模拟HR甲", Role.HR, "engineering"),
    "hr-b": ("模拟HR乙", Role.HR, "sales"),
    "manager-a": ("模拟工程负责人", Role.MANAGER, "engineering"),
}
DEV_IDS = {alias: str(uuid.uuid5(uuid.NAMESPACE_URL, f"recruitflow:dev:{alias}")) for alias in DEV_DIRECTORY}


def dev_auth_enabled() -> bool:
    return (
        os.getenv("APP_ENV", "development") == "development"
        and os.getenv("APP_MODE", "mock") in {"mock", "hybrid"}
        and os.getenv("DEV_AUTH_ENABLED", "true").lower() == "true"
    )


def seed_dev_users(session_factory=SessionLocal):
    if not dev_auth_enabled():
        return
    with session_factory() as db:
        for alias, (name, role, department) in DEV_DIRECTORY.items():
            if db.get(User, DEV_IDS[alias]) is None:
                db.add(
                    User(
                        id=DEV_IDS[alias],
                        display_name=name,
                        role=role.value,
                        department=department,
                        active=True,
                    )
                )
        db.commit()


def current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_dev_user: Annotated[str | None, Header()] = None,
) -> User:
    if not dev_auth_enabled():
        raise BusinessError(401, "UNAUTHENTICATED", "开发身份未启用；生产身份接入尚未实现")
    if request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise BusinessError(403, "FORBIDDEN", "开发身份仅允许本机使用")
    alias = x_dev_user or os.getenv("DEV_DEFAULT_USER", "admin")
    user = db.scalar(
        select(User).where(
            User.id == DEV_IDS.get(alias, alias), User.active.is_(True), User.deleted_at.is_(None)
        )
    )
    if user is None:
        raise BusinessError(401, "UNAUTHENTICATED", "开发用户不存在或已停用")
    return user


def require_writer(actor: User):
    if actor.role not in {Role.HR, Role.ADMIN}:
        raise BusinessError(403, "FORBIDDEN", "当前身份没有写入权限")


def require_admin(actor: User):
    if actor.role != Role.ADMIN:
        raise BusinessError(403, "FORBIDDEN", "仅管理员可以执行此操作")
