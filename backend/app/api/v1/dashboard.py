from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime

from app import schemas as s
from app.domain import Stage
from app.services.workbench import dashboard_data

from .common import DB, Actor, envelope

router = APIRouter()


@router.get("/dashboard/overview", response_model=s.Response[s.DashboardData])
def dashboard(
    request: Request,
    db: DB,
    actor: Actor,
    from_at: AwareDatetime | None = Query(None, alias="from"),
    to: AwareDatetime | None = None,
    position_id: s.Id | None = None,
    owner_id: s.Id | None = None,
    stage: Stage | None = None,
):
    return envelope(
        request,
        dashboard_data(
            db, actor, from_at=from_at, to=to, position_id=position_id, owner_id=owner_id, stage=stage
        ),
    )
