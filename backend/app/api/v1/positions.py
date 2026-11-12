from __future__ import annotations

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app import schemas as s
from app import services as svc
from app.core.security import require_admin
from app.db import (
    Application,
    Position,
)

from .common import DB, Actor, Key, Page, PageSize, Version, envelope, listing

router = APIRouter()


@router.get("/positions", response_model=s.ListResponse[s.PositionRead])
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


@router.get("/positions/{position_id}", response_model=s.Response[s.PositionRead])
def position_detail(position_id: s.Id, request: Request, db: DB, actor: Actor):
    return envelope(request, s.PositionRead.model_validate(svc.get_entity(db, Position, position_id, actor)))


@router.post("/positions", status_code=201, response_model=s.Response[s.PositionRead])
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


@router.patch("/positions/{position_id}", response_model=s.Response[s.PositionRead])
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


@router.delete("/positions/{position_id}", response_model=s.Response[s.DeleteResult])
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
