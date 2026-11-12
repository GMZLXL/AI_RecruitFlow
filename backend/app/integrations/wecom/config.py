import os
from typing import Literal

from app.schemas.wecom import WecomStatus


def provider() -> Literal["mock", "wecom"]:
    value = os.getenv("WECOM_PROVIDER", "mock")
    if value not in {"mock", "wecom"}:
        raise RuntimeError("WECOM_PROVIDER must be mock or wecom")
    if value == "wecom" and os.getenv("APP_MODE", "mock") != "hybrid":
        raise RuntimeError("Real WeCom requires explicit hybrid mode; production identity remains blocked")
    return "mock" if value == "mock" else "wecom"


def enabled(name: str, default="false") -> bool:
    return os.getenv(name, default).lower() == "true"


def status() -> WecomStatus:
    mode = provider()

    def state(flag, fields):
        if mode == "mock":
            return "mock_only"
        if not enabled(flag):
            return "disabled"
        return "configured_not_verified" if all(os.getenv(f) for f in fields) else "blocked_by_credentials"

    return WecomStatus(provider=mode, worker_enabled=enabled("WECOM_WORKER_ENABLED", "true"),
        callback=state("WECOM_CALLBACK_ENABLED", ["WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_CALLBACK_TOKEN", "WECOM_ENCODING_AES_KEY"]),
        sending=state("WECOM_SEND_ENABLED", ["WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_SECRET"]))
