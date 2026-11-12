from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.domain import Stage, SyncState

from .common import (
    Schema,
)


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
    mode: Literal["mock", "hybrid"] = "mock"
    note: str = "Business connectors are mock; parser provider is separately configured"


class IntegrationStatus(Schema):
    mode: Literal["mock", "hybrid"] = "mock"
    deepseek: Literal[
        "not_connected", "blocked_by_credentials", "configured_not_verified", "mode_mismatch"
    ] = "not_connected"
    parser_provider: Literal["mock", "deepseek"] = "mock"
    model: str | None = None
    tencent_docs: Literal["mock_only"] = "mock_only"
    wecom: Literal["not_connected"] = "not_connected"
