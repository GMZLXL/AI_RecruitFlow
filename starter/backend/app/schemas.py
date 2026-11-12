"""Single source for the public OpenAPI/TypeScript contract."""

from __future__ import annotations

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .domain import Outcome, Role, Stage, SyncState

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Id = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
CustomFields = dict[Literal["organization.referral_tag"], Annotated[NonEmpty, Field(max_length=120)]]
T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


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


class EntityRead(Schema):
    id: str
    version: int = Field(ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class UserRead(EntityRead):
    display_name: str
    role: Role
    department: str
    active: bool


class Identity(Schema):
    user: UserRead
    mode: Literal["mock"] = "mock"
    authentication: Literal["development_only"] = "development_only"


class PositionCreate(Schema):
    title: NonEmpty = Field(max_length=120)
    department: NonEmpty = Field(max_length=100)
    target_headcount: int = Field(default=0, ge=0)
    owner_user_id: Id | None = None


class PositionPatch(Schema):
    title: NonEmpty | None = Field(default=None, max_length=120)
    target_headcount: int | None = Field(default=None, ge=0)
    active: bool | None = None
    change_reason: NonEmpty = Field(max_length=500)


class PositionRead(EntityRead):
    title: str
    department: str
    target_headcount: int
    owner_user_id: str
    active: bool


class CandidateCreate(Schema):
    display_name: NonEmpty = Field(max_length=100)
    owner_id: Id | None = None
    custom_fields: CustomFields = Field(default_factory=dict)


class CandidatePatch(Schema):
    display_name: NonEmpty | None = Field(default=None, max_length=100)
    custom_fields: CustomFields | None = None
    change_reason: NonEmpty = Field(max_length=500)


class CandidateRead(EntityRead):
    display_name: str
    owner_id: str
    custom_fields: CustomFields


class ApplicationCreate(Schema):
    candidate_id: Id | None = None
    position_id: Id | None = None
    candidate_name: NonEmpty | None = Field(default=None, max_length=100)
    position_title: NonEmpty | None = Field(default=None, max_length=120)
    application_code: NonEmpty | None = Field(default=None, max_length=40, pattern=r"^[A-Z0-9_-]+$")
    source_channel: NonEmpty | None = Field(default=None, max_length=100)
    custom_fields: CustomFields = Field(default_factory=dict)

    @model_validator(mode="after")
    def exclusive_refs(self):
        if (self.candidate_id is None) == (self.candidate_name is None):
            raise ValueError("Exactly one of candidate_id/candidate_name is required")
        if (self.position_id is None) == (self.position_title is None):
            raise ValueError("Exactly one of position_id/position_title is required")
        return self


class ApplicationPatch(Schema):
    stage: Stage | None = None
    source_channel: NonEmpty | None = Field(default=None, max_length=100)
    custom_fields: CustomFields | None = None
    change_reason: NonEmpty = Field(max_length=500)


class ApplicationRead(EntityRead):
    application_code: str
    candidate_id: str
    candidate_name: str
    position_id: str
    position_title: str
    owner_id: str
    source_channel: str | None
    stage: Stage
    outcome: Outcome
    custom_fields: CustomFields


class ApplicationMutation(Schema):
    status: Literal["applied", "needs_confirmation"]
    application: ApplicationRead
    confirmation_id: str | None = None
    reason: str | None = None


class DeleteResult(Schema):
    id: str
    version: int
    deleted_at: AwareDatetime


class DeleteRequest(Schema):
    change_reason: NonEmpty = Field(max_length=500)


class InterviewCreate(Schema):
    round: int = Field(ge=1, le=30)
    scheduled_at: AwareDatetime
    interviewer: NonEmpty = Field(max_length=100)


class InterviewPatch(Schema):
    scheduled_at: AwareDatetime | None = None
    interviewer: NonEmpty | None = Field(default=None, max_length=100)
    status: Literal["scheduled", "completed", "cancelled"] | None = None
    result: Literal["pending", "passed", "failed", "cancelled"] | None = None
    change_reason: NonEmpty = Field(max_length=500)


class InterviewRead(EntityRead):
    application_id: str
    round: int
    scheduled_at: AwareDatetime
    interviewer: str
    status: Literal["scheduled", "completed", "cancelled"]
    result: Literal["pending", "passed", "failed", "cancelled"]
    feedback_at: AwareDatetime | None


class EventRead(Schema):
    id: str
    application_id: str | None
    actor_id: str
    source: str
    event_type: str
    before_json: dict[str, object]
    after_json: dict[str, object]
    created_at: AwareDatetime


class ConfirmationRead(EntityRead):
    application_id: str | None
    reason: str
    proposed_json: dict[str, object]
    status: str


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
    confirmation_id: str | None = None
    sync_state: Literal["pending"] | None = None
    mode: Literal["mock"] = "mock"


class SyncJob(Schema):
    id: str
    entity_type: str
    entity_id: str
    application_id: str | None
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
    new_applications: int = Field(ge=0)
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
