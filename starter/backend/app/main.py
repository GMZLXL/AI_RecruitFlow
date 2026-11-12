"""S0 local Mock baseline. Full identity, CRUD and migrations follow in S1."""

from __future__ import annotations

import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Literal, NoReturn

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from .db import Application, AuditLog, Candidate, Event, Outbox, RemoteLink, get_db, init_db, utcnow
from .schemas import (
    ApiError,
    ApplicationCreate,
    ApplicationRead,
    DashboardData,
    ErrorResponse,
    Health,
    IngestionRequest,
    IngestionResult,
    IntegrationStatus,
    ListResponse,
    Pagination,
    Response,
    Stage,
    SyncJob,
    SyncRun,
    SyncState,
)

if os.getenv("APP_MODE", "mock") != "mock" or os.getenv("APP_ENV", "development") != "development":
    raise RuntimeError(
        "S0 only supports APP_ENV=development and APP_MODE=mock; production identity is not implemented."
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI RecruitFlow Mock API",
    version="0.1.0",
    lifespan=lifespan,
    description="S0 local Mock baseline. No real DeepSeek/Tencent Docs/WeCom connections.",
    responses={code: {"model": ErrorResponse} for code in (400, 403, 404, 409, 422, 500)},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Idempotency-Key"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = "req_" + uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def error_response(request: Request, status: int, code: str, message: str, details: dict | None = None):
    body = ErrorResponse(
        error=ApiError(code=code, message=message, details=details or {}),
        request_id=request.state.request_id,
    )
    return JSONResponse(
        status_code=status, content=body.model_dump(mode="json"), headers={"X-Request-ID": body.request_id}
    )


@app.exception_handler(Exception)
async def internal_error(request: Request, _exc: Exception):
    return error_response(request, 500, "INTERNAL_ERROR", "内部处理失败，请提供请求编号排查")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if isinstance(exc, ApiException):
        return error_response(request, exc.status_code, exc.api_error.code, exc.api_error.message)
    return error_response(request, exc.status_code, "HTTP_ERROR", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Never echo raw messages, candidate data or supplied secrets in error payloads.
    fields = [{"field": ".".join(map(str, item["loc"])), "type": item["type"]} for item in exc.errors()]
    return error_response(request, 422, "INVALID_INPUT", "请求字段不符合契约", {"fields": fields})


class ApiException(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status_code=status, detail=message)
        self.api_error = ApiError(code=code, message=message)


def fail(status: int, code: str, message: str) -> NoReturn:
    raise ApiException(status, code, message)


def require_local_mock(request: Request) -> str:
    """A fixed development actor, never a browser-supplied role. Replaced by S1 RBAC."""
    if request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        fail(403, "FORBIDDEN", "S0 Mock 写操作仅允许本机访问")
    return "local-mock"


DB = Annotated[Session, Depends(get_db)]
LocalActor = Annotated[str, Depends(require_local_mock)]


def utc(value: datetime) -> datetime:
    # SQLite strips tzinfo on read; all stored values originate from utcnow().
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def fmt(a: Application) -> ApplicationRead:
    return ApplicationRead(
        id=str(a.id),
        application_code=a.code,
        candidate_id=str(a.candidate_id),
        candidate_name=a.candidate.name,
        position_title=a.position,
        stage=Stage(a.stage),
        version=a.version,
        created_at=utc(a.created_at),
        updated_at=utc(a.updated_at),
    )


def record_change(db: Session, a: Application, action: str, actor: str, event_key: str | None = None):
    db.add(Event(application_id=a.id, action=action, external_event_id=event_key))
    db.add(Outbox(application_id=a.id, version=a.version))
    db.add(
        AuditLog(
            actor_id=actor,
            action=action,
            target_id=str(a.id),
            metadata_json={"version": a.version, "stage": a.stage},
        )
    )


def new_app(db: Session, data: ApplicationCreate, actor: str, event_key: str | None = None):
    a = Application(
        code=data.application_code or "A" + uuid.uuid4().hex[:8].upper(),
        position=data.position_title,
        candidate=Candidate(name=data.candidate_name),
    )
    db.add(a)
    db.flush()
    record_change(db, a, "create_application", actor, event_key)
    db.commit()
    return fmt(a)


@app.get("/api/v1/health", response_model=Response[Health])
def health(request: Request):
    return Response(data=Health(), request_id=request.state.request_id)


@app.get("/api/v1/integrations/status", response_model=Response[IntegrationStatus])
def integration_status(request: Request):
    return Response(data=IntegrationStatus(), request_id=request.state.request_id)


@app.get("/api/v1/applications", response_model=ListResponse[ApplicationRead])
def applications(
    request: Request, db: DB, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)
):
    total = db.scalar(select(func.count(Application.id))) or 0
    rows = db.scalars(
        select(Application).order_by(Application.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return ListResponse(
        data=[fmt(a) for a in rows],
        pagination=Pagination(page=page, page_size=page_size, total=total),
        request_id=request.state.request_id,
    )


@app.post("/api/v1/applications", status_code=201, response_model=Response[ApplicationRead])
def create_application(
    request: Request,
    data: ApplicationCreate,
    db: DB,
    actor: LocalActor,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=120)] = None,
):
    event_key = f"web-create:{idempotency_key}" if idempotency_key else None
    if event_key:
        existing = db.scalar(select(Event).where(Event.external_event_id == event_key))
        if existing:
            previous = db.get(Application, existing.application_id)
            if (
                previous is None
                or previous.candidate.name != data.candidate_name
                or previous.position != data.position_title
                or (data.application_code and data.application_code != previous.code)
            ):
                fail(409, "IDEMPOTENCY_CONFLICT", "相同幂等键不能用于不同请求")
            return Response(data=fmt(previous), request_id=request.state.request_id)
    try:
        return Response(data=new_app(db, data, actor, event_key), request_id=request.state.request_id)
    except IntegrityError:
        db.rollback()
        fail(409, "APPLICATION_CODE_EXISTS", "申请编号已存在")


@app.post("/api/v1/ingestions", response_model=Response[IngestionResult])
def ingestion(request: Request, req: IngestionRequest, db: DB, actor: LocalActor):
    def result(status: Literal["applied", "needs_confirmation", "duplicate"], **kwargs):
        return Response(data=IngestionResult(status=status, **kwargs), request_id=request.state.request_id)

    event_key = f"{req.source}:{req.external_event_id}" if req.external_event_id else None
    if event_key:
        existing = db.scalar(select(Event).where(Event.external_event_id == event_key))
        if existing:
            return result("duplicate", application_id=str(existing.application_id), reason="已处理相同事件")
    # Fail closed for unsupported compound instructions; S2 implements the full parser.
    creating = re.fullmatch(r"(?:新增|添加)([^，,\s]{1,20})[，,\s]*(?:应聘|申请)([^，,\s]{2,40})", req.text)
    if creating:
        try:
            a = new_app(
                db,
                ApplicationCreate(candidate_name=creating.group(1), position_title=creating.group(2)),
                actor,
                event_key,
            )
            return result(
                "applied",
                intent="create_application",
                application_id=a.id,
                application=a,
                sync_state="pending",
            )
        except IntegrityError:
            db.rollback()
            return result("needs_confirmation", reason="事件或申请编号冲突，请检查后重试")
    match = re.fullmatch(
        r"(A[A-Z0-9_-]{3,39})\s*(一面通过|初试通过|二面通过|复试通过)", req.text, re.IGNORECASE
    )
    if not match:
        return result(
            "needs_confirmation", reason="仅支持明确的新增格式或申请编号+面试通过；复合消息请待 S2 审核"
        )
    target = db.scalar(select(Application).where(Application.code == match.group(1).upper()))
    if target is None:
        return result("needs_confirmation", reason="申请编号未找到")
    stage = Stage.INTERVIEW_2 if match.group(2) in ("一面通过", "初试通过") else Stage.OFFER
    if target.stage in ("hired", "rejected", "withdrawn") or (
        target.stage == "offer" and stage == Stage.INTERVIEW_2
    ):
        return result("needs_confirmation", reason="终态或阶段逆转必须人工确认")
    # S0 preserves the demo shortcut from applied to interview_2; S1/S2 add full transitions/results.
    if target.stage == stage:
        return result("needs_confirmation", reason="申请已处于目标阶段；请核对是否重复或属于另一轮面试")
    old_version = target.version
    try:
        changed = db.execute(
            update(Application)
            .where(Application.id == target.id, Application.version == old_version)
            .values(stage=stage.value, version=old_version + 1, updated_at=utcnow())
            .returning(Application.id)
        ).scalar_one_or_none()
        if changed is None:
            db.rollback()
            fail(409, "VERSION_CONFLICT", "记录已更新，请刷新后重试")
        db.refresh(target)
        record_change(db, target, f"update_stage:{stage.value}", actor, event_key)
        db.commit()
    except IntegrityError:
        db.rollback()
        return result("needs_confirmation", reason="重复事件冲突，请重试以读取已有结果")
    return result(
        "applied",
        intent="update_stage",
        application_id=str(target.id),
        application=fmt(target),
        sync_state="pending",
    )


@app.get("/api/v1/dashboard/overview", response_model=Response[DashboardData])
def dashboard(request: Request, db: DB):
    total = db.scalar(select(func.count(Application.id))) or 0
    stages = {
        Stage(stage): count
        for stage, count in db.execute(
            select(Application.stage, func.count(Application.id)).group_by(Application.stage)
        )
    }
    pending = db.scalar(select(func.count(Outbox.id)).where(Outbox.status == "pending")) or 0
    return Response(
        data=DashboardData(new_applications=total, by_stage=stages, pending_sync=pending),
        request_id=request.state.request_id,
    )


@app.get("/api/v1/sync/jobs", response_model=ListResponse[SyncJob])
def sync_jobs(request: Request, db: DB, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    total = db.scalar(select(func.count(Outbox.id))) or 0
    jobs = db.scalars(
        select(Outbox).order_by(Outbox.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    rows = [
        SyncJob(
            id=str(j.id),
            application_id=str(j.application_id),
            version=j.version,
            status=SyncState(j.status),
            remote_record_id=j.remote_record_id,
            attempts=j.attempts,
        )
        for j in jobs
    ]
    return ListResponse(
        data=rows,
        pagination=Pagination(page=page, page_size=page_size, total=total),
        request_id=request.state.request_id,
    )


@app.post("/api/v1/sync/run", response_model=Response[SyncRun])
def run_mock_sync(request: Request, db: DB, actor: LocalActor):
    """Only local simulation. No network calls or real credentials."""
    jobs = db.scalars(select(Outbox).where(Outbox.status == "pending").order_by(Outbox.id)).all()
    for job in jobs:
        link = db.scalar(select(RemoteLink).where(RemoteLink.application_id == job.application_id))
        if link is None:
            link = RemoteLink(
                application_id=job.application_id, remote_record_id="MOCK-" + uuid.uuid4().hex[:8]
            )
            db.add(link)
            db.flush()
        job.remote_record_id = link.remote_record_id
        job.status = "mock_synced"
        job.attempts += 1
        db.add(
            AuditLog(
                actor_id=actor,
                action="mock_sync",
                target_type="sync_outbox",
                target_id=str(job.id),
                metadata_json={"version": job.version},
            )
        )
    db.commit()
    return Response(data=SyncRun(processed=len(jobs)), request_id=request.state.request_id)
