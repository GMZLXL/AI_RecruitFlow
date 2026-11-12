"""Bounded in-memory windows for the supported single API process."""

import math
import os
import time
from collections import OrderedDict
from threading import Lock

from app.core.errors import BusinessError
from app.core.runtime import flag


class RateLimiter:
    def __init__(self):
        self.windows = OrderedDict()
        self.lock = Lock()

    def check(self, key, limit, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            since, count = self.windows.pop(key, (now, 0))
            if now - since >= 60:
                since, count = now, 0
            self.windows[key] = since, count + 1
            while len(self.windows) > 10000:
                self.windows.popitem(last=False)
            return max(1, math.ceil(60 - (now - since))) if count >= limit else 0


def limit_actor(request, actor_id):
    if not flag("RATE_LIMIT_ENABLED", "true"):
        return
    if request.method == "POST" and request.url.path in {"/api/v1/ingestions", "/api/v1/wecom/mock/messages"}:
        retry = request.app.state.rate_limiter.check("ingest:" + actor_id, int(os.getenv("INGESTION_RATE_PER_MINUTE", "30")))
        if retry:
            request.state.retry_after = retry
            raise BusinessError(429, "RATE_LIMITED", "消息录入过于频繁，请稍后再试")
