from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from app.domain import ConfirmationState, Stage

from .common import EntityRead, Id, NonEmpty, Schema
from .recruitment import ApplicationRead

Intent = Literal[
    "create_application", "update_stage", "record_result", "schedule_interview", "query", "unknown"
]
ReasonCode = Annotated[str, Field(min_length=1, max_length=120)]
SpanKey = Annotated[str, Field(min_length=1, max_length=80)]
SpanValue = Annotated[str, Field(min_length=1, max_length=200)]


class ScheduleProposal(Schema):
    round: int = Field(ge=1, le=30)
    scheduled_at: AwareDatetime | None = None
    interviewer: NonEmpty | None = Field(default=None, max_length=100)


class Extraction(Schema):
    intent: Intent
    application_code: NonEmpty | None = Field(default=None, max_length=40, pattern=r"^[A-Z0-9_-]+$")
    candidate_name: NonEmpty | None = Field(default=None, max_length=100)
    position_name: NonEmpty | None = Field(default=None, max_length=120)
    stage: Stage | None = None
    interview_round: int | None = Field(default=None, ge=1, le=30)
    interview_result: Literal["pending", "passed", "failed", "cancelled"] | None = None
    scheduled_at: AwareDatetime | None = None
    interviewer: NonEmpty | None = Field(default=None, max_length=100)
    next_interview: ScheduleProposal | None = None
    missing_fields: list[ReasonCode] = Field(default_factory=list, max_length=20)
    ambiguities: list[ReasonCode] = Field(default_factory=list, max_length=20)
    source_spans: dict[SpanKey, SpanValue] = Field(default_factory=dict, max_length=20)
    should_confirm: bool = False


class IngestionRequest(Schema):
    text: NonEmpty = Field(max_length=2000)
    external_event_id: NonEmpty | None = Field(default=None, max_length=150)
    source: Literal["manual", "wecom_mock", "wecom"] = "manual"
    execute_if_unambiguous: bool = True


class IngestionResult(Schema):
    ingestion_id: str | None = None
    status: Literal["applied", "needs_confirmation", "duplicate", "parsing", "failed"]
    reason: str | None = None
    reason_code: str | None = None
    intent: Intent | None = None
    application_id: str | None = None
    application: ApplicationRead | None = None
    confirmation_id: str | None = None
    sync_state: Literal["pending"] | None = None
    mode: Literal["mock", "hybrid"] = "mock"
    parser_provider: Literal["mock", "deepseek"] = "mock"


class IngestionRead(EntityRead):
    source: str
    external_event_id: str | None
    state: str
    error_code: str | None
    received_at: AwareDatetime
    message_excerpt: str
    extraction: Extraction | None = None
    result: IngestionResult | None = None


class ConfirmationRead(EntityRead):
    application_id: str | None
    reason: str
    status: ConfirmationState
    proposal: Extraction | None = None
    candidates: list[ApplicationRead] = Field(default_factory=list)
    message_excerpt: str = ""
    target_stage: Stage | None = None
    expected_application_version: int | None = None


class ResolveRequest(Schema):
    decision: Literal["confirm", "modify", "reject"]
    change_reason: NonEmpty = Field(max_length=500)
    application_id: Id | None = None
    expected_application_version: int | None = Field(default=None, ge=1)
    candidate_id: Id | None = None
    position_id: Id | None = None
    interview_id: Id | None = None
    create_new_candidate: bool = False
    correction: Extraction | None = None


class ResolutionResult(Schema):
    confirmation_id: str
    status: Literal["confirmed", "rejected"]
    version: int
    application: ApplicationRead | None = None
