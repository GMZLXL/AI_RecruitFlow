from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import (
    EntityRead,
    NonEmpty,
    Schema,
)
from .recruitment import ApplicationRead


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
