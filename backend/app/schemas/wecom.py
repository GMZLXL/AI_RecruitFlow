"""S5 transport/task contracts; credentials are never request/response fields."""

from typing import Literal

from pydantic import AwareDatetime, Field

from .common import EntityRead, NonEmpty, Schema

Provider = Literal["mock", "wecom"]
DeliveryState = Literal[
    "pending", "processing", "mock_sent", "accepted", "blocked", "failed", "uncertain", "cancelled"
]


class MockMessage(Schema):
    message_id: NonEmpty = Field(max_length=150)
    text: NonEmpty = Field(max_length=2000)


class InboxRead(EntityRead):
    provider: Provider
    status: Literal["pending", "processing", "completed", "failed"]
    ingestion_id: str | None
    last_error: str | None
    attempts: int


class NotificationRead(EntityRead):
    provider: Provider
    status: DeliveryState
    application_id: str | None
    recipient_name: str
    text: str
    attempts: int
    last_error: str | None
    platform_message_id: str | None
    completed_at: AwareDatetime | None


class ReminderPolicyUpdate(Schema):
    enabled: bool
    interview_hours: int = Field(ge=1, le=168)
    feedback_hours: int = Field(ge=1, le=720)
    stalled_days: int = Field(ge=1, le=365)
    change_reason: NonEmpty = Field(max_length=300)


class ReminderPolicyRead(EntityRead):
    enabled: bool
    interview_hours: int
    feedback_hours: int
    stalled_days: int
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"


class WecomStatus(Schema):
    provider: Provider
    callback: Literal["mock_only", "disabled", "blocked_by_credentials", "configured_not_verified"]
    sending: Literal["mock_only", "disabled", "blocked_by_credentials", "configured_not_verified"]
    worker_enabled: bool
    callback_path: str = "/api/v1/webhooks/wecom"
    notice: str = "只接收主动发给自建应用的消息；平台接受不代表用户已读，模拟发送不代表真实投递。"


class WecomBinding(Schema):
    external_userid: NonEmpty | None = Field(default=None, max_length=150, pattern=r"^[A-Za-z0-9_@.\-]+$")
    change_reason: NonEmpty = Field(max_length=300)


class WecomUser(EntityRead):
    display_name: str
    role: str
    external_wecom_userid: str | None


class TaskRetry(Schema):
    change_reason: NonEmpty = Field(max_length=300)
