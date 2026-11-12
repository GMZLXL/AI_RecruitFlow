"""Allowlisted operational logging: no raw messages, exception text or request URLs."""

import json
import logging
import re
from datetime import datetime, timezone


class SafeJsonFormatter(logging.Formatter):
    def format(self, record):
        event = record.getMessage()
        event = event if event in {"request_complete", "request_failed", "sync_worker_cycle_failed",
            "wecom_worker_cycle_failed", "worker_cycle_failed"} else "external_message_omitted"
        body = {"time": datetime.now(timezone.utc).isoformat(), "level": record.levelname, "event": event}
        for key in ("request_id", "route", "method", "status", "duration_ms", "error_code"):
            if record.name != "app.core.http":
                break
            value = getattr(record, key, None)
            if key == "route" and isinstance(value, str):
                # Routes are templates, never raw URLs or arbitrary unmatched paths.
                value = value if re.fullmatch(r"/[a-zA-Z0-9_/{}/.-]{0,150}", value) else "unmatched"
            if value is not None:
                body[key] = value
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    root = logging.getLogger()
    # The app owns the server logging boundary; Uvicorn's URL-bearing access handler is replaced.
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
