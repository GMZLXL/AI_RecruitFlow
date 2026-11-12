"""Deterministic authorization, state changes and transaction boundaries."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import NoReturn

from sqlalchemy import func, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from . import schemas as s
from .db import (
    Application,
    AuditLog,
    Candidate,
    Confirmation,
    Event,
    IdempotencyRecord,
    Interview,
    Outbox,
    Position,
    User,
    new_id,
    utcnow,
)
from .domain import Outcome, Role, Stage, transition_allowed, transition_requires_confirmation
from .errors import BusinessError
from .security import require_admin, require_writer


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


def create_candidate(db: Session, actor: User, data: s.CandidateCreate) -> Candidate:
    require_writer(actor)
    owner = owner_user(db, actor, data.owner_id)
    obj = Candidate(display_name=data.display_name, owner_id=owner.id, custom_fields=data.custom_fields)
    db.add(obj)
    record_change(db, obj, actor, "create_candidate")
    return obj


def create_position(db: Session, actor: User, data: s.PositionCreate) -> Position:
    require_admin(actor)
    owner = owner_user(db, actor, data.owner_user_id)
    if data.department != owner.department:
        fail(400, "INVALID_DEPARTMENT", "岗位部门必须与负责人部门一致")
    obj = Position(
        title=data.title,
        department=data.department,
        target_headcount=data.target_headcount,
        owner_user_id=owner.id,
    )
    db.add(obj)
    record_change(db, obj, actor, "create_position")
    return obj


def create_application(
    db: Session, actor: User, data: s.ApplicationCreate, event_key=None, source="manual"
) -> Application:
    require_writer(actor)
    if data.candidate_id:
        candidate = get_entity(db, Candidate, data.candidate_id, actor, write=True)
    else:
        assert data.candidate_name is not None  # validated exclusive reference branch
        candidate = create_candidate(db, actor, s.CandidateCreate(display_name=data.candidate_name))
    if data.position_id:
        position = get_entity(db, Position, data.position_id, actor)
    else:
        choices = db.scalars(
            select(Position).where(
                visibility(Position, actor), Position.active.is_(True), Position.title == data.position_title
            )
        ).all()
        if len(choices) > 1:
            fail(409, "POSITION_AMBIGUOUS", "岗位名称不唯一，请使用 position_id")
        if choices:
            position = choices[0]
        else:
            # The S0 convenience branch remains available to administrators only.
            assert data.position_title is not None
            position = create_position(
                db, actor, s.PositionCreate(title=data.position_title, department=actor.department)
            )
    owner = owner_user(db, actor, candidate.owner_id)
    if not position.active or position.department != owner.department:
        fail(403, "FORBIDDEN", "岗位已停用或不在负责人所属部门")
    obj = Application(
        application_code=data.application_code or "A" + new_id().replace("-", "")[:12].upper(),
        candidate=candidate,
        position=position,
        owner_id=owner.id,
        source_channel=data.source_channel,
        custom_fields=data.custom_fields,
    )
    db.add(obj)
    record_change(db, obj, actor, "create_application", event_key=event_key, source=source)
    return obj


def patch_application(
    db: Session,
    actor: User,
    obj: Application,
    data: s.ApplicationPatch,
    expected: int,
    event_key=None,
    source="manual",
) -> s.ApplicationMutation:
    if obj.version != expected:
        fail(409, "VERSION_CONFLICT", "版本已更新，请刷新后重试")
    before = snapshot(obj)
    target = data.stage
    if target is not None and transition_requires_confirmation(Stage(obj.stage), target):
        confirmation = Confirmation(
            application_id=obj.id,
            owner_id=obj.owner_id,
            reason="TERMINAL_REVERSAL",
            proposed_json={
                "stage": target.value,
                "expected_version": expected,
                "change_reason": redact_reason(data.change_reason),
            },
        )
        db.add(confirmation)
        record_change(db, confirmation, actor, "request_terminal_reversal")
        return s.ApplicationMutation(
            status="needs_confirmation",
            application=application_read(obj),
            confirmation_id=confirmation.id,
            reason="终态逆转需要人工确认",
        )
    if target is not None and not transition_allowed(Stage(obj.stage), target):
        fail(409, "INVALID_STAGE_TRANSITION", "不允许跳阶段或逆转，请核对当前阶段")
    values = data.model_dump(exclude={"change_reason"}, exclude_none=True)
    if target is not None:
        values["stage"] = target.value
        values["outcome"] = (
            target.value if target in {Stage.HIRED, Stage.REJECTED, Stage.WITHDRAWN} else "pending"
        )
    if not values:
        fail(400, "NO_CHANGES", "未提供任何可修改字段")
    conditional_update(db, obj, expected, values)
    record_change(db, obj, actor, "update_application", before, data.change_reason, event_key, source)
    return s.ApplicationMutation(status="applied", application=application_read(obj))


def patch_entity(db: Session, actor: User, obj, data, expected: int):
    before = snapshot(obj)
    values = data.model_dump(exclude={"change_reason"}, exclude_none=True)
    if not values:
        fail(400, "NO_CHANGES", "未提供任何可修改字段")
    conditional_update(db, obj, expected, values)
    record_change(db, obj, actor, "update_" + obj.__tablename__, before, data.change_reason)
    return obj


def soft_delete(db: Session, actor: User, obj, expected: int, reason: str) -> s.DeleteResult:
    if obj.deleted_at is not None:
        fail(404, "NOT_FOUND", "记录已删除")
    if isinstance(obj, (Candidate, Position)):
        column = Application.candidate_id if isinstance(obj, Candidate) else Application.position_id
        if db.scalar(
            select(func.count(Application.id)).where(column == obj.id, Application.deleted_at.is_(None))
        ):
            fail(409, "ACTIVE_APPLICATIONS_EXIST", "请先处理关联申请，不能删除仍在使用的资料")
    before = snapshot(obj)
    deleted_at = utcnow()
    conditional_update(db, obj, expected, {"deleted_at": deleted_at})
    record_change(db, obj, actor, "delete_" + obj.__tablename__, before, reason)
    return s.DeleteResult(id=obj.id, version=obj.version, deleted_at=deleted_at)


def touch_application(db: Session, actor: User, obj: Application):
    before = snapshot(obj)
    conditional_update(db, obj, obj.version, {})
    record_change(db, obj, actor, "interview_changed", before)


def create_interview(db: Session, actor: User, obj: Application, data: s.InterviewCreate, expected: int):
    if obj.version != expected:
        fail(409, "VERSION_CONFLICT", "申请版本已更新")
    if obj.stage not in {Stage.INTERVIEW_1, Stage.INTERVIEW_2}:
        fail(409, "INVALID_STAGE_TRANSITION", "仅面试阶段可以安排面试")
    if data.scheduled_at <= utcnow():
        fail(400, "INVALID_INTERVIEW_TIME", "面试时间必须在将来")
    interview = Interview(application_id=obj.id, **data.model_dump())
    db.add(interview)
    record_change(db, interview, actor, "create_interview")
    touch_application(db, actor, obj)
    return s.InterviewRead.model_validate(interview)


def patch_interview(
    db: Session, actor: User, obj: Interview, application: Application, data: s.InterviewPatch, expected: int
):
    values = data.model_dump(exclude={"change_reason"}, exclude_none=True)
    status = values.get("status", obj.status)
    result = values.get("result", obj.result)
    if obj.status != "scheduled" and status != obj.status:
        fail(409, "INVALID_INTERVIEW_TRANSITION", "已完成或取消的面试不能直接逆转")
    if (
        (status == "completed" and result not in {"passed", "failed"})
        or (status == "scheduled" and result != "pending")
        or (status == "cancelled" and result != "cancelled")
    ):
        fail(400, "INVALID_INTERVIEW_RESULT", "面试状态与结果不一致")
    if data.scheduled_at is not None and data.scheduled_at <= utcnow():
        fail(400, "INVALID_INTERVIEW_TIME", "面试时间必须在将来")
    if not values:
        fail(400, "NO_CHANGES", "未提供任何可修改字段")
    if status == "completed":
        values["feedback_at"] = utcnow()
    before = snapshot(obj)
    conditional_update(db, obj, expected, values)
    record_change(db, obj, actor, "update_interview", before, data.change_reason)
    touch_application(db, actor, application)
    return s.InterviewRead.model_validate(obj)
