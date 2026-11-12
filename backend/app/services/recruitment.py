from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas as s
from app.core.security import require_admin, require_writer
from app.db import (
    Application,
    Candidate,
    Confirmation,
    Position,
    User,
    new_id,
    utcnow,
)
from app.domain import Stage, transition_allowed, transition_requires_confirmation

from .common import (
    application_read,
    conditional_update,
    fail,
    get_entity,
    owner_user,
    record_change,
    redact_reason,
    snapshot,
    visibility,
)


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
