"""Public API contract. Generate OpenAPI and TypeScript after changing these models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_serializer

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Stage(StrEnum):
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW_1 = "interview_1"
    INTERVIEW_2 = "interview_2"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Response(Schema, Generic[T]):
    data: T
    request_id: str


class Pagination(Schema):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class ListResponse(Response[list[T]], Generic[T]):
    pagination: Pagination


class ApiError(Schema):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(Schema):
    error: ApiError
    request_id: str


class ApplicationCreate(Schema):
    candidate_name: NonEmpty = Field(max_length=100)
    position_title: NonEmpty = Field(max_length=120)
    application_code: NonEmpty | None = Field(default=None, max_length=40, pattern=r"^[A-Z0-9_-]+$")


class ApplicationRead(Schema):
    id: str
    application_code: str
    candidate_id: str
    candidate_name: str
    position_id: str | None = None
    position_title: str
    stage: Stage
    version: int = Field(ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_serializer("created_at", "updated_at")
    def serialize_time(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


class IngestionRequest(Schema):
    text: NonEmpty = Field(max_length=2000)
    external_event_id: NonEmpty | None = Field(default=None, max_length=150)
    source: Literal["manual", "wecom_mock"] = "manual"


class IngestionResult(Schema):
    status: Literal["applied", "needs_confirmation", "duplicate"]
    reason: str | None = None
    intent: Literal["create_application", "update_stage"] | None = None
    application_id: str | None = None
    application: ApplicationRead | None = None
    sync_state: Literal["pending"] | None = None
    mode: Literal["mock"] = "mock"


class SyncState(StrEnum):
    PENDING = "pending"
    MOCK_SYNCED = "mock_synced"


class SyncJob(Schema):
    id: str
    application_id: str
    version: int = Field(ge=1)
    status: SyncState
    remote_record_id: str | None
    attempts: int = Field(ge=0)
    mode: Literal["mock"] = "mock"


class SyncRun(Schema):
    processed: int = Field(ge=0)
    mode: Literal["mock"] = "mock"
    warning: str = "仅模拟，不代表写入腾讯文档"


class DashboardData(Schema):
    new_applications: int = Field(ge=0, description="S0 为申请总数，未实施日期筛选")
    by_stage: dict[Stage, int]
    pending_sync: int = Field(ge=0)
    mode: Literal["mock"] = "mock"


class Health(Schema):
    status: Literal["ok"] = "ok"
    mode: Literal["mock"] = "mock"
    note: str = "No external API used"


class IntegrationStatus(Schema):
    mode: Literal["mock"] = "mock"
    deepseek: Literal["not_connected"] = "not_connected"
    tencent_docs: Literal["mock_only"] = "mock_only"
    wecom: Literal["not_connected"] = "not_connected"
