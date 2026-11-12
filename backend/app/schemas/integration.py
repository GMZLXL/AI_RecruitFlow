from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.domain import Outcome, Stage, SyncState

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
    provider: Literal["mock", "tencent_docs"]
    mode: Literal["mock", "real"]
    revision: int = Field(ge=1)
    cycle_attempts: int = Field(ge=0)
    internal_only: bool
    last_error: str | None
    next_retry_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class SyncRun(Schema):
    accepted: bool = True
    message: str = "已请求后台处理，实际结果请查询任务状态"


class SyncRetry(Schema):
    reason: str = Field(min_length=1, max_length=300)


class SyncSummary(Schema):
    counts: dict[SyncState, int]
    last_success_at: datetime | None
    worker_enabled: bool
    provider: Literal["mock", "tencent_docs"]
    tencent_docs: Literal["blocked_by_credentials", "blocked_by_schema"]
    message: str


class ApplicationProjection(Schema):
    schema_version: Literal[1] = 1
    application_id: str
    application_code: str
    candidate_name: str
    position_title: str
    stage: Stage
    outcome: Outcome
    version: int = Field(ge=1)
    deleted: bool = False
    updated_at: datetime


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
    tencent_docs: Literal["blocked_by_credentials", "blocked_by_schema"] = "blocked_by_credentials"
    sync_provider: Literal["mock", "tencent_docs"] = "mock"
    wecom: Literal["not_connected"] = "not_connected"
