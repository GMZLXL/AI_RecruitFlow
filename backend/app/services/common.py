from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import NoReturn

from sqlalchemy import select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from app import schemas as s
from app.core.errors import BusinessError
from app.core.security import require_admin, require_writer
from app.db import (
    Application,
    AuditLog,
    Candidate,
    Confirmation,
    Event,
    IdempotencyRecord,
    Outbox,
    Position,
    User,
    utcnow,
)
from app.domain import Outcome, Role, Stage


def fail(status: int, code: str, message: str) -> NoReturn:
    raise BusinessError(status, code, message)


def visibility(model, actor: User, *, include_deleted=False):
    alive = true() if include_deleted else model.deleted_at.is_(None)
    if actor.role == Role.ADMIN:
        return alive
    if model is Position:
        return alive & (model.department == actor.department)
    if model is Candidate:
        owners = select(User.id).where(User.department == actor.department)
        return alive & (model.owner_id == actor.id if actor.role == Role.HR else model.owner_id.in_(owners))
    if model is Application:
        positions = select(Position.id).where(Position.department == actor.department)
        return alive & (
            model.owner_id == actor.id if actor.role == Role.HR else model.position_id.in_(positions)
        )
    if model is Confirmation:
        apps = select(Application.id).where(visibility(Application, actor))
        return alive & (
            model.owner_id == actor.id if actor.role == Role.HR else model.application_id.in_(apps)
        )
    raise ValueError("Unsupported visibility model")


def get_entity(db: Session, model, entity_id: str, actor: User, *, write=False, allow_deleted=False):
    obj = db.get(model, entity_id)
    if obj is None or (obj.deleted_at is not None and not allow_deleted):
        fail(404, "NOT_FOUND", "记录不存在")
    visible = db.scalar(
        select(model.id).where(model.id == entity_id, visibility(model, actor, include_deleted=allow_deleted))
    )
    if visible is None:
        fail(403, "FORBIDDEN", "记录不在当前用户授权范围内")
    if write:
        require_writer(actor)
        if model is Position:
            require_admin(actor)
        elif actor.role != Role.ADMIN and obj.owner_id != actor.id:
            fail(403, "FORBIDDEN", "只能修改本人负责的记录")
    return obj


def application_read(obj: Application) -> s.ApplicationRead:
    return s.ApplicationRead(
        id=obj.id,
        application_code=obj.application_code,
        candidate_id=obj.candidate_id,
        candidate_name=obj.candidate.display_name,
        position_id=obj.position_id,
        position_title=obj.position.title,
        owner_id=obj.owner_id,
        source_channel=obj.source_channel,
        stage=Stage(obj.stage),
        outcome=Outcome(obj.outcome),
        custom_fields=obj.custom_fields,
        version=obj.version,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


def snapshot(obj) -> dict:
    data = {}
    for attribute in inspect(type(obj)).column_attrs:
        if attribute.key == "contact_encrypted":
            continue
        value = getattr(obj, attribute.key)
        data[attribute.key] = (
            value.isoformat().replace("+00:00", "Z") if isinstance(value, datetime) else value
        )
    return data


def redact_reason(reason: str) -> str:
    reason = re.sub(r"\b1[3-9]\d{9}\b", "[phone]", reason)
    return re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", reason)


def record_change(
    db: Session,
    obj,
    actor: User,
    action: str,
    before: dict | None = None,
    reason: str = "",
    event_key: str | None = None,
    source="manual",
):
    db.flush()
    db.refresh(obj)  # normalize just-inserted timestamps through the database UTC type
    after = snapshot(obj)
    entity_type = obj.__tablename__
    application_id = obj.id if isinstance(obj, Application) else getattr(obj, "application_id", None)
    db.add(
        AuditLog(
            actor_id=actor.id,
            action=action,
            target_type=entity_type,
            target_id=obj.id,
            metadata_json={"before": before or {}, "after": after, "reason": redact_reason(reason)},
        )
    )
    db.add(
        Outbox(
            entity_type=entity_type,
            entity_id=obj.id,
            application_id=application_id,
            version=obj.version,
            op="delete" if obj.deleted_at else "upsert",
            payload_json={"schema_version": 1, "entity": after},
        )
    )
    if isinstance(obj, Application):
        db.add(
            Event(
                application_id=obj.id,
                actor_id=actor.id,
                event_type=action,
                external_event_key=event_key,
                source=source,
                before_json=before or {},
                after_json=after,
            )
        )


def conditional_update(db: Session, obj, expected: int, values: dict):
    if obj.version != expected:
        fail(409, "VERSION_CONFLICT", "版本已更新，请刷新后重试")
    model = type(obj)
    changed = db.execute(
        update(model)
        .where(model.id == obj.id, model.version == expected, model.deleted_at.is_(None))
        .values(**values, version=expected + 1, updated_at=utcnow())
        .returning(model.id)
    ).scalar_one_or_none()
    if changed is None:
        fail(409, "VERSION_CONFLICT", "版本已更新，请刷新后重试")
    db.refresh(obj)


def mutate(db: Session, actor: User, operation: str, key: str | None, payload: dict, change):
    require_writer(actor)
    if not key or not key.strip() or len(key) > 150:
        fail(400, "IDEMPOTENCY_KEY_REQUIRED", "业务写入必须提供有效的 Idempotency-Key")
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    existing = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == actor.id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        )
    )
    if existing:
        if existing.request_hash != digest:
            fail(409, "IDEMPOTENCY_CONFLICT", "相同幂等键不能用于不同请求")
        return existing.response_json
    try:
        result = change()
        response = result.model_dump(mode="json") if isinstance(result, s.Schema) else result
        db.add(
            IdempotencyRecord(
                actor_id=actor.id, operation=operation, key=key, request_hash=digest, response_json=response
            )
        )
        db.commit()
        return response
    except IntegrityError:
        db.rollback()
        fail(409, "CONSTRAINT_CONFLICT", "编号、事件或版本发生唯一约束冲突，请刷新后重试")
    except Exception:
        db.rollback()
        raise


def owner_user(db: Session, actor: User, owner_id: str | None) -> User:
    target_id = owner_id or actor.id
    if actor.role != Role.ADMIN and target_id != actor.id:
        fail(403, "FORBIDDEN", "不能指定其他负责人")
    owner = db.get(User, target_id)
    if owner is None or not owner.active or owner.deleted_at or owner.role not in {Role.HR, Role.ADMIN}:
        fail(400, "INVALID_OWNER", "负责人不存在、已停用或没有业务写权限")
    return owner
