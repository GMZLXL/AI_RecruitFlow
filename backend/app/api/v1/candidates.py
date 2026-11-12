from __future__ import annotations

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app import schemas as s
from app import services as svc
from app.db import (
    Application,
    Candidate,
)

from .common import DB, Actor, Key, Page, PageSize, Version, envelope, listing

router = APIRouter()


@router.get("/candidates", response_model=s.ListResponse[s.CandidateRead])
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


@router.get("/candidates/{candidate_id}", response_model=s.Response[s.CandidateRead])
def candidate_detail(candidate_id: s.Id, request: Request, db: DB, actor: Actor):
    return envelope(
        request, s.CandidateRead.model_validate(svc.get_entity(db, Candidate, candidate_id, actor))
    )


@router.post("/candidates", status_code=201, response_model=s.Response[s.CandidateRead])
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


@router.patch("/candidates/{candidate_id}", response_model=s.Response[s.CandidateRead])
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


@router.delete("/candidates/{candidate_id}", response_model=s.Response[s.DeleteResult])
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
