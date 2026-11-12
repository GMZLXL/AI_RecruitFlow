from __future__ import annotations

from sqlalchemy.orm import Session

from app import schemas as s
from app.db import (
    Application,
    Interview,
    User,
    utcnow,
)
from app.domain import Stage

from .common import (
    conditional_update,
    fail,
    record_change,
    snapshot,
)
from .recruitment import touch_application


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
