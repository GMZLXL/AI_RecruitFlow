from typing import Literal

from pydantic import AwareDatetime

from .common import Schema


class AuthConfig(Schema):
    authentication: Literal["development_only", "sso_cookie"]
    mode: Literal["mock", "hybrid"]
    login_url: str | None = None
    logout_url: str | None = None


class WorkerHealth(Schema):
    name: Literal["sync", "wecom"]
    enabled: bool
    last_success_at: AwareDatetime | None
    last_cycle_at: AwareDatetime | None
    last_error: str | None


class OpsStatus(Schema):
    database: Literal["ok"] = "ok"
    schema_revision: str
    worker_role: Literal["leader", "standby", "disabled", "starting"]
    lease_healthy: bool
    heartbeat_at: AwareDatetime | None
    workers: list[WorkerHealth]
    sync_counts: dict[str, int]
    inbox_counts: dict[str, int]
    notification_counts: dict[str, int]
    oldest_pending_sync_at: AwareDatetime | None
    rate_limit_enabled: bool
    log_format: Literal["safe_json"] = "safe_json"
