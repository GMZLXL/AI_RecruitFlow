from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app import schemas as s
from app.core.security import require_writer
from app.db import Confirmation, IngestionJob, User
from app.domain import Role
from app.integrations.parsers.base import Parser
from app.integrations.parsers.factory import get_parser
from app.services.common import get_entity, mutate, visibility
from app.services.confirmations import confirmation_read, resolve
from app.services.ingestion import ingest

from .common import DB, Actor, Key, Page, PageSize, Version, envelope, listing

router = APIRouter()


@router.post("/ingestions", response_model=s.Response[s.IngestionResult])
async def ingestion(
    request: Request,
    req: s.IngestionRequest,
    db: DB,
    actor: Actor,
    parser: Annotated[Parser, Depends(get_parser)],
):
    require_writer(actor)
    actor_id = actor.id
    db.close()  # release the authentication read transaction before any parser/network work
    return envelope(request, await ingest(actor_id, req, parser))


@router.get("/ingestions", response_model=s.ListResponse[s.IngestionRead])
def ingestions(request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20):
    query = select(IngestionJob).where(IngestionJob.deleted_at.is_(None))
    if actor.role != Role.ADMIN:
        owners = (
            select(User.id).where(User.department == actor.department)
            if actor.role == Role.MANAGER
            else [actor.id]
        )
        query = query.where(IngestionJob.actor_id.in_(owners))

    def read(job):
        raw = job.extracted_json
        return s.IngestionRead(
            id=job.id,
            version=job.version,
            created_at=job.created_at,
            updated_at=job.updated_at,
            source=job.source,
            external_event_id=job.external_event_id,
            state=job.state,
            error_code=job.error_code,
            received_at=job.received_at,
            message_excerpt=raw.get("message_excerpt", ""),
            extraction=s.Extraction.model_validate(raw["extraction"]) if raw.get("extraction") else None,
            result=s.IngestionResult.model_validate(raw["result"]) if raw.get("result") else None,
        )

    return listing(
        request, db, query.order_by(IngestionJob.received_at.desc(), IngestionJob.id), page, page_size, read
    )


@router.get("/confirmations", response_model=s.ListResponse[s.ConfirmationRead])
def confirmations(
    request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20, status: str = "pending"
):
    query = select(Confirmation).where(visibility(Confirmation, actor), Confirmation.status == status)
    return listing(
        request,
        db,
        query.order_by(Confirmation.created_at.desc(), Confirmation.id),
        page,
        page_size,
        lambda obj: confirmation_read(db, obj, actor),
    )


@router.post("/confirmations/{confirmation_id}/resolve", response_model=s.Response[s.ResolutionResult])
def confirmation_resolve(
    confirmation_id: s.Id,
    data: s.ResolveRequest,
    request: Request,
    db: DB,
    actor: Actor,
    if_match: Version,
    key: Key = None,
):
    obj = get_entity(db, Confirmation, confirmation_id, actor, write=True)
    return envelope(
        request,
        mutate(
            db,
            actor,
            "resolve_confirmation:" + confirmation_id,
            key,
            {**data.model_dump(mode="json"), "version": if_match},
            lambda: resolve(db, actor, obj, data, if_match),
        ),
    )
