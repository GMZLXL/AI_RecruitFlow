from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app import schemas as s
from app import services as svc
from app.db import (
    Application,
    Outbox,
)
from app.domain import Role, Stage

from .common import DB, Actor, envelope

router = APIRouter()


@router.get("/dashboard/overview", response_model=s.Response[s.DashboardData])
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
    jobs = select(func.count(Outbox.id)).where(Outbox.status.in_(["pending", "processing", "failed", "dead"]))
    if actor.role != Role.ADMIN:
        jobs = jobs.where(Outbox.application_id.in_(visible_ids))
    return envelope(
        request, s.DashboardData(new_applications=total, by_stage=stages, pending_sync=db.scalar(jobs) or 0)
    )
