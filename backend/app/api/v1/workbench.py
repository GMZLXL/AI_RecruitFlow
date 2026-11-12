from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import func, select

from app import schemas as s
from app import services as svc
from app.db import Application, Offer
from app.domain import FORWARD_STAGES, Stage
from app.services.offers import create_offer, respond_offer
from app.services.workbench import history_query, history_read, options, tasks_query

from .common import DB, Actor, Key, Page, PageSize, Version, envelope, listing

router = APIRouter()


@router.get("/recruitment/options", response_model=s.Response[s.RecruitmentOptions])
def recruitment_options(request: Request, db: DB, actor: Actor, keyword: str = Query("", max_length=120)):
    return envelope(request, options(db, actor, keyword))


@router.get("/tasks", response_model=s.ListResponse[s.TaskRead])
def tasks(
    request: Request,
    db: DB,
    actor: Actor,
    page: Page = 1,
    page_size: PageSize = 20,
    kind: s.TaskKind | None = None,
    owner_id: s.Id | None = None,
    position_id: s.Id | None = None,
    from_at: AwareDatetime | None = Query(None, alias="from"),
    to: AwareDatetime | None = None,
):
    query = tasks_query(actor, kind=kind, owner_id=owner_id, position_id=position_id, from_at=from_at, to=to)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.execute(query.offset((page - 1) * page_size).limit(page_size)).mappings()
    return {
        **envelope(request, [s.TaskRead(id=row["kind"] + ":" + row["source_id"], **row) for row in rows]),
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


@router.get("/settings/policy", response_model=s.Response[s.PolicyRead])
def settings_policy(request: Request, actor: Actor):
    return envelope(
        request,
        s.PolicyRead(
            stage_transitions={
                stage: sorted(FORWARD_STAGES.get(stage, set()), key=lambda value: value.value)
                for stage in Stage
            }
        ),
    )


@router.get("/applications/{application_id}/history", response_model=s.ListResponse[s.HistoryRead])
def application_history(
    application_id: s.Id, request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20
):
    svc.get_entity(db, Application, application_id, actor)
    return listing(
        request, db, history_query(application_id), page, page_size, lambda row: history_read(db, row)
    )


@router.get("/applications/{application_id}/offer", response_model=s.Response[s.OfferRead | None])
def application_offer(application_id: s.Id, request: Request, db: DB, actor: Actor):
    svc.get_entity(db, Application, application_id, actor)
    offer = db.scalar(select(Offer).where(Offer.application_id == application_id, Offer.deleted_at.is_(None)))
    return envelope(request, s.OfferRead.model_validate(offer) if offer else None)


@router.post("/applications/{application_id}/offer", response_model=s.Response[s.OfferRead], status_code=201)
def offer_create(
    application_id: s.Id,
    req: s.OfferCreate,
    request: Request,
    db: DB,
    actor: Actor,
    expected: Version,
    key: Key = None,
):
    application = svc.get_entity(db, Application, application_id, actor, write=True)
    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "create_offer:" + application_id,
            key,
            {**req.model_dump(mode="json"), "version": expected},
            lambda: create_offer(db, actor, application, req, expected),
        ),
    )


@router.patch("/applications/{application_id}/offer", response_model=s.Response[s.OfferRead])
def offer_patch(
    application_id: s.Id,
    req: s.OfferPatch,
    request: Request,
    db: DB,
    actor: Actor,
    expected: Version,
    key: Key = None,
):
    application = svc.get_entity(db, Application, application_id, actor, write=True)
    offer = db.scalar(select(Offer).where(Offer.application_id == application_id, Offer.deleted_at.is_(None)))
    if offer is None:
        svc.fail(404, "NOT_FOUND", "尚未登记Offer发出记录")
    return envelope(
        request,
        svc.mutate(
            db,
            actor,
            "respond_offer:" + application_id,
            key,
            {**req.model_dump(mode="json"), "version": expected},
            lambda: respond_offer(db, actor, application, offer, req, expected),
        ),
    )
