from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from app import schemas as s
from app import services as svc
from app.db import (
    Application,
    Interview,
)

from .common import DB, Actor, Key, Page, PageSize, Version, envelope, listing

router = APIRouter()


@router.get("/applications/{application_id}/interviews", response_model=s.ListResponse[s.InterviewRead])
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


@router.post(
    "/applications/{application_id}/interviews",
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


@router.get("/interviews/{interview_id}", response_model=s.Response[s.InterviewRead])
def interview_detail(interview_id: s.Id, request: Request, db: DB, actor: Actor):
    obj, _ = interview_and_application(db, interview_id, actor)
    return envelope(request, s.InterviewRead.model_validate(obj))


@router.patch("/interviews/{interview_id}", response_model=s.Response[s.InterviewRead])
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


@router.delete("/interviews/{interview_id}", response_model=s.Response[s.DeleteResult])
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
