from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import select

from app import schemas as s
from app import services as svc
from app.db import (
    Application,
    Event,
)
from app.domain import Stage
from app.services.workbench import filtered_applications

from .common import DB, Actor, Key, Page, PageSize, Version, envelope, listing

router = APIRouter()


@router.get("/applications", response_model=s.ListResponse[s.ApplicationRead])
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
    query = filtered_applications(actor, keyword=keyword, position_id=position_id, owner_id=owner_id,
                                  stage=stage, source_channel=source_channel, from_at=from_at, to=to)
    if candidate_id:
        query = query.where(Application.candidate_id == candidate_id)
    order = {
        "created_desc": Application.created_at.desc(),
        "updated_desc": Application.updated_at.desc(),
        "code_asc": Application.application_code.asc(),
    }[sort]
    return listing(request, db, query.order_by(order, Application.id), page, page_size, svc.application_read)


@router.get("/applications/{application_id}", response_model=s.Response[s.ApplicationRead])
def application_detail(application_id: s.Id, request: Request, db: DB, actor: Actor):
    return envelope(request, svc.application_read(svc.get_entity(db, Application, application_id, actor)))


@router.post("/applications", status_code=201, response_model=s.Response[s.ApplicationRead])
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


@router.patch("/applications/{application_id}", response_model=s.Response[s.ApplicationMutation])
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


@router.delete("/applications/{application_id}", response_model=s.Response[s.DeleteResult])
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


@router.get("/applications/{application_id}/events", response_model=s.ListResponse[s.EventRead])
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
