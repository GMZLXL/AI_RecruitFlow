"""Local Mock API. S1 adds migrated domain entities and development RBAC."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from . import schemas as s
from . import services as svc
from .db import (
    Application,
    AuditLog,
    Candidate,
    Confirmation,
    Event,
    IngestionJob,
    Interview,
    Outbox,
    Position,
    RemoteLink,
    User,
    get_db,
    init_db,
    new_id,
)
from .domain import Role, Stage
from .errors import BusinessError
from .security import DEV_IDS, current_user, require_admin, require_writer, seed_dev_users

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


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = "req_" + uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def error_response(request: Request, status: int, code: str, message: str, details: dict | None = None):
    body = s.ErrorResponse(
        error=s.ApiError(code=code, message=message, details=details or {}),
        request_id=request.state.request_id,
    )
    return JSONResponse(
        status_code=status, content=body.model_dump(mode="json"), headers={"X-Request-ID": body.request_id}
    )


@app.exception_handler(BusinessError)
async def business_error(request: Request, exc: BusinessError):
    return error_response(request, exc.status, exc.code, exc.message)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return error_response(request, exc.status_code, "HTTP_ERROR", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    fields = [{"field": ".".join(map(str, item["loc"])), "type": item["type"]} for item in exc.errors()]
    return error_response(request, 422, "INVALID_INPUT", "请求字段不符合契约", {"fields": fields})


@app.exception_handler(Exception)
async def internal_error(request: Request, _exc: Exception):
    return error_response(request, 500, "INTERNAL_ERROR", "内部处理失败，请提供请求编号排查")


DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(current_user)]
Key = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=150)]
Version = Annotated[int, Header(alias="If-Match", ge=1)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def envelope(request: Request, data):
    return {"data": data, "request_id": request.state.request_id}


def listing(request: Request, db: Session, query, page: int, page_size: int, read):
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        **envelope(request, [read(row) for row in rows]),
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


@app.get("/api/v1/health", response_model=s.Response[s.Health])
def health(request: Request):
    return envelope(request, s.Health())


@app.get("/api/v1/ready", response_model=s.Response[s.Health])
def ready(request: Request, db: DB, actor: Actor):
    db.execute(select(1))
    return envelope(request, s.Health(note="Database schema and connection ready"))


@app.get("/api/v1/me", response_model=s.Response[s.Identity])
def me(request: Request, actor: Actor):
    return envelope(request, s.Identity(user=s.UserRead.model_validate(actor)))


@app.get("/api/v1/dev/users", response_model=s.Response[list[s.UserRead]])
def development_users(request: Request, db: DB, actor: Actor):
    users = db.scalars(select(User).where(User.id.in_(DEV_IDS.values()), User.active.is_(True))).all()
    return envelope(request, [s.UserRead.model_validate(user) for user in users])


@app.get("/api/v1/integrations/status", response_model=s.Response[s.IntegrationStatus])
def integration_status(request: Request, actor: Actor):
    require_admin(actor)
    return envelope(request, s.IntegrationStatus())


@app.get("/api/v1/positions", response_model=s.ListResponse[s.PositionRead])
def positions(
    request: Request,
    db: DB,
    actor: Actor,
    page: Page = 1,
    page_size: PageSize = 20,
    keyword: str | None = Query(None, max_length=120),
    active: bool | None = None,
):
    query = select(Position).where(svc.visibility(Position, actor))
    if keyword:
        query = query.where(Position.title.contains(keyword, autoescape=True))
    if active is not None:
        query = query.where(Position.active == active)
    return listing(
        request,
        db,
        query.order_by(Position.created_at.desc(), Position.id),
        page,
        page_size,
        s.PositionRead.model_validate,
    )


@app.get("/api/v1/positions/{position_id}", response_model=s.Response[s.PositionRead])
def position_detail(position_id: s.Id, request: Request, db: DB, actor: Actor):
    return envelope(request, s.PositionRead.model_validate(svc.get_entity(db, Position, position_id, actor)))


@app.post("/api/v1/positions", status_code=201, response_model=s.Response[s.PositionRead])
def position_create(data: s.PositionCreate, request: Request, db: DB, actor: Actor, key: Key = None):
    require_admin(actor)
    result = svc.mutate(
        db,
        actor,
        "create_position",
        key,
        data.model_dump(mode="json"),
        lambda: s.PositionRead.model_validate(svc.create_position(db, actor, data)),
    )
    return envelope(request, result)


@app.patch("/api/v1/positions/{position_id}", response_model=s.Response[s.PositionRead])
def position_patch(
    position_id: s.Id,
    data: s.PositionPatch,
    request: Request,
    db: DB,
    actor: Actor,
    if_match: Version,
    key: Key = None,
):
    obj = svc.get_entity(db, Position, position_id, actor, write=True)

    def change():
        svc.patch_entity(db, actor, obj, data, if_match)
        if data.title is not None:
            for application in db.scalars(
                select(Application).where(Application.position_id == obj.id, Application.deleted_at.is_(None))
            ):
                svc.touch_application(db, actor, application)
        return s.PositionRead.model_validate(obj)

    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "patch_position:" + position_id,
            key,
            {**data.model_dump(mode="json"), "version": if_match},
            change,
        ),
    )


@app.delete("/api/v1/positions/{position_id}", response_model=s.Response[s.DeleteResult])
def position_delete(
    position_id: s.Id,
    data: s.DeleteRequest,
    request: Request,
    db: DB,
    actor: Actor,
    if_match: Version,
    key: Key = None,
):
    obj = svc.get_entity(db, Position, position_id, actor, write=True, allow_deleted=True)
    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "delete_position:" + position_id,
            key,
            {**data.model_dump(), "version": if_match},
            lambda: svc.soft_delete(db, actor, obj, if_match, data.change_reason),
        ),
    )


@app.get("/api/v1/candidates", response_model=s.ListResponse[s.CandidateRead])
def candidates(
    request: Request,
    db: DB,
    actor: Actor,
    page: Page = 1,
    page_size: PageSize = 20,
    keyword: str | None = Query(None, max_length=100),
    owner_id: str | None = None,
):
    query = select(Candidate).where(svc.visibility(Candidate, actor))
    if keyword:
        query = query.where(Candidate.display_name.contains(keyword, autoescape=True))
    if owner_id:
        query = query.where(Candidate.owner_id == owner_id)
    return listing(
        request,
        db,
        query.order_by(Candidate.created_at.desc(), Candidate.id),
        page,
        page_size,
        s.CandidateRead.model_validate,
    )


@app.get("/api/v1/candidates/{candidate_id}", response_model=s.Response[s.CandidateRead])
def candidate_detail(candidate_id: s.Id, request: Request, db: DB, actor: Actor):
    return envelope(
        request, s.CandidateRead.model_validate(svc.get_entity(db, Candidate, candidate_id, actor))
    )


@app.post("/api/v1/candidates", status_code=201, response_model=s.Response[s.CandidateRead])
def candidate_create(data: s.CandidateCreate, request: Request, db: DB, actor: Actor, key: Key = None):
    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "create_candidate",
            key,
            data.model_dump(mode="json"),
            lambda: s.CandidateRead.model_validate(svc.create_candidate(db, actor, data)),
        ),
    )


@app.patch("/api/v1/candidates/{candidate_id}", response_model=s.Response[s.CandidateRead])
def candidate_patch(
    candidate_id: s.Id,
    data: s.CandidatePatch,
    request: Request,
    db: DB,
    actor: Actor,
    if_match: Version,
    key: Key = None,
):
    obj = svc.get_entity(db, Candidate, candidate_id, actor, write=True)

    def change():
        svc.patch_entity(db, actor, obj, data, if_match)
        if data.display_name is not None:
            for application in db.scalars(
                select(Application).where(
                    Application.candidate_id == obj.id, Application.deleted_at.is_(None)
                )
            ):
                svc.touch_application(db, actor, application)
        return s.CandidateRead.model_validate(obj)

    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "patch_candidate:" + candidate_id,
            key,
            {**data.model_dump(mode="json"), "version": if_match},
            change,
        ),
    )


@app.delete("/api/v1/candidates/{candidate_id}", response_model=s.Response[s.DeleteResult])
def candidate_delete(
    candidate_id: s.Id,
    data: s.DeleteRequest,
    request: Request,
    db: DB,
    actor: Actor,
    if_match: Version,
    key: Key = None,
):
    obj = svc.get_entity(db, Candidate, candidate_id, actor, write=True, allow_deleted=True)
    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "delete_candidate:" + candidate_id,
            key,
            {**data.model_dump(), "version": if_match},
            lambda: svc.soft_delete(db, actor, obj, if_match, data.change_reason),
        ),
    )


@app.get("/api/v1/applications", response_model=s.ListResponse[s.ApplicationRead])
def applications(
    request: Request,
    db: DB,
    actor: Actor,
    page: Page = 1,
    page_size: PageSize = 20,
    keyword: str | None = Query(None, max_length=120),
    stage: Stage | None = None,
    candidate_id: str | None = None,
    position_id: str | None = None,
    owner_id: str | None = None,
    source_channel: str | None = None,
    from_at: AwareDatetime | None = Query(None, alias="from"),
    to: AwareDatetime | None = None,
    sort: Literal["created_desc", "updated_desc", "code_asc"] = "created_desc",
):
    query = select(Application).where(svc.visibility(Application, actor))
    if keyword:
        query = query.where(
            Application.application_code.contains(keyword, autoescape=True)
            | Application.candidate.has(Candidate.display_name.contains(keyword, autoescape=True))
        )
    for column, value in (
        (Application.stage, stage),
        (Application.candidate_id, candidate_id),
        (Application.position_id, position_id),
        (Application.owner_id, owner_id),
        (Application.source_channel, source_channel),
    ):
        if value is not None:
            query = query.where(column == value)
    if from_at is not None:
        query = query.where(Application.created_at >= from_at)
    if to is not None:
        query = query.where(Application.created_at < to)
    order = {
        "created_desc": Application.created_at.desc(),
        "updated_desc": Application.updated_at.desc(),
        "code_asc": Application.application_code.asc(),
    }[sort]
    return listing(request, db, query.order_by(order, Application.id), page, page_size, svc.application_read)


@app.get("/api/v1/applications/{application_id}", response_model=s.Response[s.ApplicationRead])
def application_detail(application_id: s.Id, request: Request, db: DB, actor: Actor):
    return envelope(request, svc.application_read(svc.get_entity(db, Application, application_id, actor)))


@app.post("/api/v1/applications", status_code=201, response_model=s.Response[s.ApplicationRead])
def create_application(request: Request, data: s.ApplicationCreate, db: DB, actor: Actor, key: Key = None):
    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "create_application",
            key,
            data.model_dump(mode="json"),
            lambda: svc.application_read(svc.create_application(db, actor, data)),
        ),
    )


@app.patch("/api/v1/applications/{application_id}", response_model=s.Response[s.ApplicationMutation])
def application_patch(
    application_id: s.Id,
    data: s.ApplicationPatch,
    request: Request,
    db: DB,
    actor: Actor,
    if_match: Version,
    key: Key = None,
):
    obj = svc.get_entity(db, Application, application_id, actor, write=True)
    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "patch_application:" + application_id,
            key,
            {**data.model_dump(mode="json"), "version": if_match},
            lambda: svc.patch_application(db, actor, obj, data, if_match),
        ),
    )


@app.delete("/api/v1/applications/{application_id}", response_model=s.Response[s.DeleteResult])
def application_delete(
    application_id: s.Id,
    data: s.DeleteRequest,
    request: Request,
    db: DB,
    actor: Actor,
    if_match: Version,
    key: Key = None,
):
    obj = svc.get_entity(db, Application, application_id, actor, write=True, allow_deleted=True)
    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "delete_application:" + application_id,
            key,
            {**data.model_dump(), "version": if_match},
            lambda: svc.soft_delete(db, actor, obj, if_match, data.change_reason),
        ),
    )


@app.get("/api/v1/applications/{application_id}/events", response_model=s.ListResponse[s.EventRead])
def application_events(
    application_id: s.Id, request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20
):
    svc.get_entity(db, Application, application_id, actor)
    return listing(
        request,
        db,
        select(Event)
        .where(Event.application_id == application_id)
        .order_by(Event.created_at.desc(), Event.id),
        page,
        page_size,
        s.EventRead.model_validate,
    )


@app.get("/api/v1/applications/{application_id}/interviews", response_model=s.ListResponse[s.InterviewRead])
def interviews(
    application_id: s.Id, request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20
):
    svc.get_entity(db, Application, application_id, actor)
    return listing(
        request,
        db,
        select(Interview)
        .where(Interview.application_id == application_id, Interview.deleted_at.is_(None))
        .order_by(Interview.scheduled_at, Interview.id),
        page,
        page_size,
        s.InterviewRead.model_validate,
    )


@app.post(
    "/api/v1/applications/{application_id}/interviews",
    status_code=201,
    response_model=s.Response[s.InterviewRead],
)
def interview_create(
    application_id: s.Id,
    data: s.InterviewCreate,
    request: Request,
    db: DB,
    actor: Actor,
    if_match: Version,
    key: Key = None,
):
    obj = svc.get_entity(db, Application, application_id, actor, write=True)
    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "create_interview:" + application_id,
            key,
            {**data.model_dump(mode="json"), "version": if_match},
            lambda: svc.create_interview(db, actor, obj, data, if_match),
        ),
    )


def interview_and_application(db, interview_id, actor, *, write=False):
    obj = db.get(Interview, interview_id)
    if obj is None or obj.deleted_at is not None:
        svc.fail(404, "NOT_FOUND", "面试不存在")
    application = svc.get_entity(db, Application, obj.application_id, actor, write=write)
    return obj, application


@app.get("/api/v1/interviews/{interview_id}", response_model=s.Response[s.InterviewRead])
def interview_detail(interview_id: s.Id, request: Request, db: DB, actor: Actor):
    obj, _ = interview_and_application(db, interview_id, actor)
    return envelope(request, s.InterviewRead.model_validate(obj))


@app.patch("/api/v1/interviews/{interview_id}", response_model=s.Response[s.InterviewRead])
def interview_patch(
    interview_id: s.Id,
    data: s.InterviewPatch,
    request: Request,
    db: DB,
    actor: Actor,
    if_match: Version,
    key: Key = None,
):
    obj, application = interview_and_application(db, interview_id, actor, write=True)
    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "patch_interview:" + interview_id,
            key,
            {**data.model_dump(mode="json"), "version": if_match},
            lambda: svc.patch_interview(db, actor, obj, application, data, if_match),
        ),
    )


@app.delete("/api/v1/interviews/{interview_id}", response_model=s.Response[s.DeleteResult])
def interview_delete(
    interview_id: s.Id,
    data: s.DeleteRequest,
    request: Request,
    db: DB,
    actor: Actor,
    if_match: Version,
    key: Key = None,
):
    obj = db.get(Interview, interview_id)
    if obj is None:
        svc.fail(404, "NOT_FOUND", "面试不存在")
    application = svc.get_entity(db, Application, obj.application_id, actor, write=True)

    def change():
        result = svc.soft_delete(db, actor, obj, if_match, data.change_reason)
        svc.touch_application(db, actor, application)
        return result

    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "delete_interview:" + interview_id,
            key,
            {**data.model_dump(), "version": if_match},
            change,
        ),
    )


@app.get("/api/v1/confirmations", response_model=s.ListResponse[s.ConfirmationRead])
def confirmations(request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20):
    return listing(
        request,
        db,
        select(Confirmation)
        .where(svc.visibility(Confirmation, actor))
        .order_by(Confirmation.created_at.desc(), Confirmation.id),
        page,
        page_size,
        s.ConfirmationRead.model_validate,
    )


@app.post("/api/v1/ingestions", response_model=s.Response[s.IngestionResult])
def ingestion(request: Request, req: s.IngestionRequest, db: DB, actor: Actor):
    require_writer(actor)
    external_id = req.external_event_id or new_id()
    message_hash = hashlib.sha256(req.text.encode()).hexdigest()
    existing = db.scalar(
        select(IngestionJob).where(
            IngestionJob.source == req.source, IngestionJob.external_event_id == external_id
        )
    )
    if existing:
        if existing.actor_id != actor.id:
            svc.fail(403, "FORBIDDEN", "不能重放其他用户接入的事件")
        if existing.message_hash != message_hash:
            svc.fail(409, "IDEMPOTENCY_CONFLICT", "相同事件ID不能用于不同消息")
        previous = s.IngestionResult.model_validate(existing.extracted_json["result"])
        if previous.application_id:
            svc.get_entity(db, Application, previous.application_id, actor)
        if previous.status == "applied":
            previous.status = "duplicate"
        return envelope(request, previous)
    event_key = hashlib.sha256(f"{req.source}:{external_id}".encode()).hexdigest()
    legacy_event = db.scalar(
        select(Event).where(Event.external_event_key == event_key, Event.source == "legacy_s0")
    )
    if legacy_event and legacy_event.application_id:
        previous_application = svc.get_entity(db, Application, legacy_event.application_id, actor)
        return envelope(
            request,
            s.IngestionResult(
                status="duplicate",
                application_id=previous_application.id,
                reason="已迁移的S0历史事件，不重复执行",
            ),
        )

    def change():
        job = IngestionJob(
            actor_id=actor.id, source=req.source, external_event_id=external_id, message_hash=message_hash
        )
        db.add(job)
        result = s.IngestionResult(
            status="needs_confirmation",
            reason="仅支持明确新增或当前面试阶段的唯一编号更新；完整Parser/审核在S2实施",
        )
        creating = re.fullmatch(
            r"(?:新增|添加)([^，,\s]{1,20})[，,\s]*(?:应聘|申请)([^，,\s]{2,40})", req.text
        )
        match = re.fullmatch(
            r"(A[A-Z0-9_-]{3,39})\s*(一面通过|初试通过|二面通过|复试通过)", req.text, re.IGNORECASE
        )
        if creating:
            same_name = db.scalar(
                select(Candidate.id).where(
                    svc.visibility(Candidate, actor), Candidate.display_name == creating.group(1)
                )
            )
            if same_name:
                result.reason = "存在同名候选人，请使用候选人ID或待S2人工确认"
            else:
                obj = svc.create_application(
                    db,
                    actor,
                    s.ApplicationCreate(candidate_name=creating.group(1), position_title=creating.group(2)),
                    event_key,
                    req.source,
                )
                result = s.IngestionResult(
                    status="applied",
                    intent="create_application",
                    application_id=obj.id,
                    application=svc.application_read(obj),
                    sync_state="pending",
                )
        elif match:
            target = db.scalar(
                select(Application).where(
                    Application.application_code == match.group(1).upper(), Application.deleted_at.is_(None)
                )
            )
            if target is not None:
                svc.get_entity(db, Application, target.id, actor, write=True)
                first = match.group(2) in {"一面通过", "初试通过"}
                expected_stage = Stage.INTERVIEW_1 if first else Stage.INTERVIEW_2
                if target.stage == expected_stage:
                    changed = svc.patch_application(
                        db,
                        actor,
                        target,
                        s.ApplicationPatch(
                            stage=Stage.INTERVIEW_2 if first else Stage.OFFER,
                            change_reason="Mock明确面试阶段更新",
                        ),
                        target.version,
                        event_key,
                        req.source,
                    )
                    result = s.IngestionResult(
                        status="applied",
                        intent="update_stage",
                        application_id=target.id,
                        application=changed.application,
                        sync_state="pending",
                    )
                else:
                    result.reason = "当前阶段与消息轮次不一致，不能跳阶段或逆转"
        job.state = result.status
        job.extracted_json = {"result": result.model_dump(mode="json")}
        svc.record_change(db, job, actor, "ingest_" + result.status)
        return result

    result = svc.mutate(db, actor, "ingest:" + req.source, external_id, req.model_dump(mode="json"), change)
    return envelope(request, result)


@app.get("/api/v1/dashboard/overview", response_model=s.Response[s.DashboardData])
def dashboard(request: Request, db: DB, actor: Actor):
    scope = svc.visibility(Application, actor)
    total = db.scalar(select(func.count(Application.id)).where(scope)) or 0
    stages = {
        Stage(stage): count
        for stage, count in db.execute(
            select(Application.stage, func.count(Application.id)).where(scope).group_by(Application.stage)
        )
    }
    visible_ids = select(Application.id).where(scope)
    jobs = select(func.count(Outbox.id)).where(Outbox.status == "pending")
    if actor.role != Role.ADMIN:
        jobs = jobs.where(Outbox.application_id.in_(visible_ids))
    return envelope(
        request, s.DashboardData(new_applications=total, by_stage=stages, pending_sync=db.scalar(jobs) or 0)
    )


@app.get("/api/v1/sync/jobs", response_model=s.ListResponse[s.SyncJob])
def sync_jobs(request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20):
    require_admin(actor)
    return listing(
        request,
        db,
        select(Outbox).order_by(Outbox.created_at.desc(), Outbox.id),
        page,
        page_size,
        s.SyncJob.model_validate,
    )


@app.post("/api/v1/sync/run", response_model=s.Response[s.SyncRun])
def run_mock_sync(request: Request, db: DB, actor: Actor, key: Key = None):
    require_admin(actor)

    def change():
        jobs = db.scalars(
            select(Outbox).where(Outbox.status == "pending").order_by(Outbox.created_at, Outbox.id)
        ).all()
        for job in jobs:
            if job.entity_type == "applications":
                link = db.scalar(
                    select(RemoteLink).where(
                        RemoteLink.entity_type == job.entity_type,
                        RemoteLink.entity_id == job.entity_id,
                        RemoteLink.provider == "mock",
                    )
                )
                if link is None:
                    link = RemoteLink(
                        entity_type=job.entity_type,
                        entity_id=job.entity_id,
                        application_id=job.application_id,
                        remote_record_id="MOCK-" + new_id()[:8],
                        provider="mock",
                        last_synced_version=0,
                    )
                    db.add(link)
                    db.flush()
                link.last_synced_version = max(link.last_synced_version, job.version)
                job.remote_record_id = link.remote_record_id
            job.status = "mock_synced"
            job.attempts += 1
            db.add(
                AuditLog(
                    actor_id=actor.id,
                    action="mock_sync",
                    target_type="sync_outbox",
                    target_id=job.id,
                    metadata_json={
                        "version": job.version,
                        "mode": "mock",
                        "internal_only": job.entity_type != "applications",
                    },
                )
            )
        return s.SyncRun(processed=len(jobs))

    return envelope(request, svc.mutate(db, actor, "run_mock_sync", key, {}, change))
