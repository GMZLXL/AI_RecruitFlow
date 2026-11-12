from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.domain import Outcome, Stage

from .common import (
    CustomFields,
    EntityRead,
    Id,
    NonEmpty,
    Schema,
)


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
    scheduled_at: AwareDatetime | None
    interviewer: str | None
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
