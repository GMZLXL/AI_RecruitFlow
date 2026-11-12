from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import schemas as s
from app.api.v1 import router
from app.core.http import configure_http
from app.core.limits import RateLimiter
from app.core.logging import configure_logging
from app.core.runtime import auth_mode, production, public_origin, validate_runtime
from app.core.security import seed_dev_users
from app.db import (
    init_db,
)
from app.integrations.smartsheet.factory import sync_provider
from app.integrations.wecom.config import provider as wecom_provider
from app.jobs.runtime import supervise
from app.jobs.sync_worker import sync_loop, worker_enabled
from app.jobs.wecom_worker import wecom_loop
from app.jobs.wecom_worker import worker_enabled as wecom_worker_enabled

configure_logging()
validate_runtime()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime()
    init_db()
    seed_dev_users()
    from app.core.secret_store import master_key

    master_key()
    if production():
        from app.services.ai_settings import connection

        ai = connection()
        if ai.provider == "deepseek" and (not ai.api_key.get_secret_value() or os.getenv("APP_MODE") != "hybrid"):
            raise RuntimeError("Managed AI configuration requires authorized hybrid mode and usable credentials")
    sync_provider()
    wecom_provider()
    _app.state.sync_wakeup = asyncio.Event()
    _app.state.wecom_wakeup = asyncio.Event()
    _app.state.rate_limiter = RateLimiter()
    runners = []
    if worker_enabled():
        runners.append(lambda: sync_loop(_app.state.sync_wakeup))
    if wecom_worker_enabled():
        runners.append(lambda: wecom_loop(_app.state.wecom_wakeup))
    _app.state.worker_role = "starting" if runners else "disabled"
    worker = asyncio.create_task(supervise(_app, runners)) if runners else None
    try:
        yield
    finally:
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker


app = FastAPI(
    title="AI RecruitFlow Mock API",
    version="0.7.0",
    lifespan=lifespan,
    description="S6 server-validated SSO sessions, safe operations and single-instance deployment; real providers remain subject to authorization.",
    responses={code: {"model": s.ErrorResponse} for code in (400, 401, 403, 404, 409, 413, 422, 429, 500, 503)},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", public_origin() if production() else "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=auth_mode() == "sso",
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Idempotency-Key", "If-Match", "X-Dev-User", "X-CSRF-Token"],
    expose_headers=["X-Request-ID"],
)
configure_http(app)
app.include_router(router, prefix="/api/v1")
