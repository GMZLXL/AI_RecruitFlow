from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import schemas as s
from app.api.v1 import router
from app.core.http import configure_http
from app.core.security import seed_dev_users
from app.db import (
    init_db,
)

if os.getenv("APP_ENV", "development") != "development" or os.getenv("APP_MODE", "mock") != "mock":
    raise RuntimeError(
        "S1 only supports APP_ENV=development and APP_MODE=mock; production identity is not implemented"
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    seed_dev_users()
    yield


app = FastAPI(
    title="AI RecruitFlow Mock API",
    version="0.2.0",
    lifespan=lifespan,
    description="S1 domain, migration and development RBAC. No real external connections.",
    responses={code: {"model": s.ErrorResponse} for code in (400, 401, 403, 404, 409, 422, 500)},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Idempotency-Key", "If-Match", "X-Dev-User"],
    expose_headers=["X-Request-ID"],
)
configure_http(app)
app.include_router(router, prefix="/api/v1")
