from datetime import date
from typing import Literal

from pydantic import AwareDatetime, Field

from app.domain import Stage

from .common import EntityRead, NonEmpty, Schema
from .identity import UserRead
from .recruitment import PositionRead


class OfferCreate(Schema):
    sent_at: AwareDatetime
    change_reason: NonEmpty = Field(max_length=500)


class OfferPatch(Schema):
    status: Literal["accepted", "declined"]
    responded_at: AwareDatetime
    change_reason: NonEmpty = Field(max_length=500)


class OfferRead(EntityRead):
    application_id: str
    status: Literal["sent", "accepted", "declined"]
    sent_at: AwareDatetime
    responded_at: AwareDatetime | None


class WeeklyCount(Schema):
    week: date
    count: int = Field(ge=0)


class PositionProgress(Schema):
    position_id: str
    title: str
    applications: int = Field(ge=0)
    hired: int = Field(ge=0)
    target_headcount: int = Field(ge=0)


class DashboardData(Schema):
    new_applications: int = Field(ge=0)
    candidates: int = Field(ge=0)
    upcoming_interviews: int = Field(ge=0)
    pending_feedback: int = Field(ge=0)
    offers_sent: int = Field(ge=0)
    offers_accepted: int = Field(ge=0)
    offers_declined: int = Field(ge=0)
    offer_acceptance_rate: float | None
    hired_applications: int = Field(ge=0)
    by_stage: dict[Stage, int]
    weekly_new: list[WeeklyCount]
    by_position: list[PositionProgress]
    pending_sync: int = Field(ge=0)
    mode: Literal["mock"] = "mock"
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    population: str = "按申请创建时间与授权范围筛选；面试与Offer指标统计这些申请关联的实际记录"


class RecruitmentOptions(Schema):
    positions: list[PositionRead]
    owners: list[UserRead]
    limit: int = 100


TaskKind = Literal["interview", "feedback", "review", "stalled", "sync"]


class TaskRead(Schema):
    id: str
    kind: TaskKind
    application_id: str | None
    application_code: str | None
    candidate_name: str | None
    position_title: str | None
    at: AwareDatetime
    source_id: str
    title: str


class HistoryRead(Schema):
    id: str
    action: str
    actor_name: str
    reason: str
    changes: dict[str, str]
    created_at: AwareDatetime


class PolicyRead(Schema):
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    stalled_days: int = 7
    stage_transitions: dict[Stage, list[Stage]]
    notice: str = "待办来自实际记录；自动提醒与企微推送尚未启用。模拟身份仅用于开发。"
