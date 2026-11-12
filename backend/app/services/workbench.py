from datetime import timedelta

from sqlalchemy import Date, case, cast, func, literal, or_, select, union_all

from app import schemas as s
from app.db import (
    Application,
    AuditLog,
    Candidate,
    Confirmation,
    Interview,
    Offer,
    Outbox,
    Position,
    User,
    utcnow,
)
from app.domain import TERMINAL_STAGES, Role, Stage
from app.integrations.parsers.privacy import redact

from .common import fail, visibility


def filtered_applications(
    actor,
    *,
    keyword=None,
    position_id=None,
    owner_id=None,
    stage=None,
    source_channel=None,
    from_at=None,
    to=None,
):
    if from_at is not None and to is not None and from_at > to:
        fail(422, "INVALID_DATE_RANGE", "开始时间不能晚于结束时间")
    query = select(Application).where(visibility(Application, actor))
    if keyword:
        query = query.where(
            Application.application_code.contains(keyword, autoescape=True)
            | Application.candidate.has(Candidate.display_name.contains(keyword, autoescape=True))
        )
    for column, value in (
        (Application.position_id, position_id),
        (Application.owner_id, owner_id),
        (Application.stage, stage),
        (Application.source_channel, source_channel),
    ):
        if value is not None:
            query = query.where(column == value)
    if from_at is not None:
        query = query.where(Application.created_at >= from_at)
    if to is not None:
        query = query.where(Application.created_at < to)
    return query


def dashboard_data(db, actor, **filters) -> s.DashboardData:
    scoped = filtered_applications(actor, **filters).subquery()
    ids = select(scoped.c.id)
    total, candidates = db.execute(
        select(func.count(), func.count(func.distinct(scoped.c.candidate_id))).select_from(scoped)
    ).one()
    stages = {
        Stage(stage): count
        for stage, count in db.execute(select(scoped.c.stage, func.count()).group_by(scoped.c.stage))
    }
    interview_base = (
        Interview.application_id.in_(ids),
        Interview.deleted_at.is_(None),
        Interview.status == "scheduled",
    )
    upcoming = (
        db.scalar(
            select(func.count())
            .select_from(Interview)
            .where(*interview_base, Interview.scheduled_at >= utcnow())
        )
        or 0
    )
    feedback = (
        db.scalar(
            select(func.count())
            .select_from(Interview)
            .where(*interview_base, Interview.scheduled_at < utcnow())
        )
        or 0
    )
    offers = dict(
        db.execute(
            select(Offer.status, func.count())
            .where(Offer.application_id.in_(ids), Offer.deleted_at.is_(None))
            .group_by(Offer.status)
        ).all()
    )
    accepted, declined = offers.get("accepted", 0), offers.get("declined", 0)
    if db.bind.dialect.name == "sqlite":
        week = func.date(scoped.c.created_at, "+8 hours", "weekday 0", "-6 days")
    else:
        week = cast(func.date_trunc("week", func.timezone("Asia/Shanghai", scoped.c.created_at)), Date)
    weekly = [
        s.WeeklyCount(week=key, count=count)
        for key, count in db.execute(select(week, func.count()).group_by(week).order_by(week))
    ]
    progress = [
        s.PositionProgress(
            position_id=pid, title=title, target_headcount=target, applications=count, hired=hired
        )
        for pid, title, target, count, hired in db.execute(
            select(
                Position.id,
                Position.title,
                Position.target_headcount,
                func.count(scoped.c.id),
                func.sum(case((scoped.c.stage == "hired", 1), else_=0)),
            )
            .join(scoped, scoped.c.position_id == Position.id)
            .group_by(Position.id, Position.title, Position.target_headcount)
            .order_by(Position.title)
        )
    ]
    pending = (
        db.scalar(
            select(func.count())
            .select_from(Outbox)
            .where(
                Outbox.entity_type == "applications",
                Outbox.entity_id.in_(ids),
                Outbox.status.in_(["pending", "processing", "failed", "dead"]),
            )
        )
        or 0
    )
    return s.DashboardData(
        new_applications=total,
        candidates=candidates,
        by_stage=stages,
        upcoming_interviews=upcoming,
        pending_feedback=feedback,
        offers_sent=sum(offers.values()),
        offers_accepted=accepted,
        offers_declined=declined,
        offer_acceptance_rate=accepted / (accepted + declined) if accepted + declined else None,
        hired_applications=stages.get(Stage.HIRED, 0),
        weekly_new=weekly,
        by_position=progress,
        pending_sync=pending,
    )


def options(db, actor, keyword="") -> s.RecruitmentOptions:
    positions = select(Position).where(visibility(Position, actor), Position.active.is_(True))
    owners = select(User).where(
        User.active.is_(True), User.deleted_at.is_(None), User.role.in_([Role.HR, Role.ADMIN])
    )
    if actor.role == Role.HR:
        owners = owners.where(User.id == actor.id)
    elif actor.role == Role.MANAGER:
        owners = owners.where(User.department == actor.department)
    if keyword:
        positions = positions.where(Position.title.contains(keyword, autoescape=True))
        owners = owners.where(User.display_name.contains(keyword, autoescape=True))
    return s.RecruitmentOptions(
        positions=[
            s.PositionRead.model_validate(row)
            for row in db.scalars(positions.order_by(Position.title, Position.id).limit(100))
        ],
        owners=[
            s.UserRead.model_validate(row)
            for row in db.scalars(owners.order_by(User.display_name, User.id).limit(100))
        ],
    )


def tasks_query(actor, *, kind=None, owner_id=None, position_id=None, from_at=None, to=None):
    ids = filtered_applications(actor, owner_id=owner_id, position_id=position_id).with_only_columns(
        Application.id
    )

    def row(model, task_kind, at, title):
        return (
            select(
                model.id.label("source_id"),
                literal(task_kind).label("kind"),
                at.label("at"),
                Application.id.label("application_id"),
                Application.application_code,
                Candidate.display_name.label("candidate_name"),
                Position.title.label("position_title"),
                literal(title).label("title"),
            )
            .select_from(model)
            .join(Application, model.application_id == Application.id)
            .join(Candidate, Application.candidate_id == Candidate.id)
            .join(Position, Application.position_id == Position.id)
            .where(Application.id.in_(ids))
        )

    now = utcnow()
    interview = row(Interview, "interview", Interview.scheduled_at, "即将面试").where(
        Interview.deleted_at.is_(None), Interview.status == "scheduled", Interview.scheduled_at >= now
    )
    feedback = row(Interview, "feedback", Interview.scheduled_at, "面试待反馈").where(
        Interview.deleted_at.is_(None), Interview.status == "scheduled", Interview.scheduled_at < now
    )
    review = select(
        Confirmation.id.label("source_id"),
        literal("review").label("kind"),
        Confirmation.created_at.label("at"),
        Application.id.label("application_id"),
        Application.application_code,
        Candidate.display_name.label("candidate_name"),
        Position.title.label("position_title"),
        literal("AI变更待审核").label("title"),
    )
    review = (
        review.select_from(Confirmation)
        .outerjoin(Application, Confirmation.application_id == Application.id)
        .outerjoin(Candidate, Application.candidate_id == Candidate.id)
        .outerjoin(Position, Application.position_id == Position.id)
        .where(visibility(Confirmation, actor), Confirmation.status == "pending")
    )
    if owner_id:
        review = review.where(Confirmation.owner_id == owner_id)
    if position_id:
        review = review.where(Application.position_id == position_id)
    stalled = (
        select(
            Application.id.label("source_id"),
            literal("stalled").label("kind"),
            Application.updated_at.label("at"),
            Application.id.label("application_id"),
            Application.application_code,
            Candidate.display_name.label("candidate_name"),
            Position.title.label("position_title"),
            literal("超过7天未更新").label("title"),
        )
        .join(Candidate)
        .join(Position)
        .where(
            Application.id.in_(ids),
            Application.stage.not_in([s.value for s in TERMINAL_STAGES]),
            Application.updated_at < now - timedelta(days=7),
        )
    )
    latest = (
        select(Outbox.entity_id, func.max(Outbox.version).label("version"))
        .where(Outbox.entity_type == "applications")
        .group_by(Outbox.entity_id)
        .subquery()
    )
    failed = (
        row(Outbox, "sync", Outbox.created_at, "申请同步异常")
        .join(latest, (Outbox.entity_id == latest.c.entity_id) & (Outbox.version == latest.c.version))
        .where(Outbox.entity_type == "applications", Outbox.status.in_(["failed", "dead"]))
    )
    tasks = union_all(interview, feedback, review, stalled, failed).subquery()
    query = select(tasks)
    if kind:
        query = query.where(tasks.c.kind == kind)
    if from_at is not None and to is not None and from_at > to:
        fail(422, "INVALID_DATE_RANGE", "开始时间不能晚于结束时间")
    if from_at:
        query = query.where(tasks.c.at >= from_at)
    if to:
        query = query.where(tasks.c.at < to)
    return query.order_by(tasks.c.at, tasks.c.source_id)


def history_query(application_id):
    targets = [AuditLog.target_type == "applications", AuditLog.target_id == application_id]
    return (
        select(AuditLog)
        .where(
            or_(
                targets[0] & targets[1],
                (AuditLog.target_type == "interviews")
                & AuditLog.target_id.in_(
                    select(Interview.id).where(Interview.application_id == application_id)
                ),
                (AuditLog.target_type == "offers")
                & AuditLog.target_id.in_(select(Offer.id).where(Offer.application_id == application_id)),
                (AuditLog.target_type == "confirmations")
                & AuditLog.target_id.in_(
                    select(Confirmation.id).where(Confirmation.application_id == application_id)
                ),
            )
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
    )


def history_read(db, audit):
    before = audit.metadata_json.get("before", {})
    after = audit.metadata_json.get("after", {})
    changes = {
        key: f"{before.get(key, '—')} → {after.get(key)}"
        for key in ("stage", "status", "result", "scheduled_at", "interviewer", "source_channel")
        if key in after and before.get(key) != after[key]
    }
    actor = db.get(User, audit.actor_id)
    return s.HistoryRead(
        id=audit.id,
        action=audit.action,
        actor_name=actor.display_name if actor else "历史操作人",
        reason=redact(audit.metadata_json.get("reason", "")),
        changes=changes,
        created_at=audit.created_at,
    )
