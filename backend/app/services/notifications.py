"""Fact-based reminder generation and a fenced notification delivery queue."""

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app import schemas as s
from app.core.errors import BusinessError
from app.core.security import SYNC_ACTOR_ID
from app.db import (
    Application,
    Interview,
    Notification,
    Outbox,
    Reminder,
    ReminderPolicy,
    SessionLocal,
    User,
    new_id,
    utcnow,
)
from app.integrations.wecom.config import provider
from app.integrations.wecom.sender import SendResult, sender

from .common import conditional_update, fail, get_entity, record_change, snapshot

POLICY_ID = "a3958afe-1892-4ef2-b415-435c3fe2ca85"
TERMINAL = {"hired", "rejected", "withdrawn"}


def policy(db):
    row = db.get(ReminderPolicy, POLICY_ID)
    if row is None:
        # Tests may clear configuration rows; production migration seeds the singleton.
        row = ReminderPolicy(id=POLICY_ID)
        db.add(row)
        db.flush()
    return row


def update_policy(db, actor, req, expected):
    row = policy(db)
    before = snapshot(row)
    conditional_update(db, row, expected, req.model_dump(exclude={"change_reason"}))
    record_change(db, row, actor, "update_reminder_policy", before, req.change_reason)
    return s.ReminderPolicyRead.model_validate(row)


def reminder_key(kind, source_id, time, owner_id):
    return f"{kind}:{source_id}:{time.isoformat()}:{owner_id}"


def latest_sync(db, application_id):
    return db.scalar(select(Outbox).where(Outbox.entity_type == "applications", Outbox.entity_id == application_id)
        .order_by(Outbox.version.desc()).limit(1))


def fact_valid(db, reminder, application, settings, now):
    if not settings.enabled or reminder.recipient_id != application.owner_id:
        return False
    if reminder.reminder_type in {"interview", "feedback"}:
        interview = db.get(Interview, reminder.source_id)
        if not interview or interview.deleted_at or interview.status != "scheduled" or not interview.scheduled_at:
            return False
        if reminder.dedupe_key != reminder_key(reminder.reminder_type, interview.id, interview.scheduled_at, application.owner_id):
            return False
        if reminder.reminder_type == "interview":
            return now < interview.scheduled_at <= now + timedelta(hours=settings.interview_hours)
        return interview.scheduled_at <= now - timedelta(hours=settings.feedback_hours)
    if reminder.reminder_type == "stalled":
        return (application.updated_at <= now - timedelta(days=settings.stalled_days)
            and reminder.dedupe_key == reminder_key("stalled", application.id, application.updated_at, application.owner_id))
    if reminder.reminder_type == "sync":
        job = latest_sync(db, application.id)
        return job is not None and job.id == reminder.source_id and job.status in {"failed", "dead"}
    return False


def generate_reminders():
    with SessionLocal() as db:
        settings = policy(db)
        if not settings.enabled:
            db.commit()
            return 0
        actor = db.get(User, SYNC_ACTOR_ID)
        assert actor is not None, "System actor missing"
        now = utcnow()
        count = 0

        def queue(application, kind, source_id, anchor, due, label):
            nonlocal count
            key = reminder_key(kind, source_id, anchor, application.owner_id)
            if db.scalar(select(Reminder.id).where(Reminder.dedupe_key == key)):
                return
            row = Reminder(application_id=application.id, reminder_type=kind, source_id=source_id,
                recipient_id=application.owner_id, due_at=due, dedupe_key=key, status="queued")
            db.add(row)
            record_change(db, row, actor, "queue_reminder")
            notice = Notification(dedupe_key="reminder:" + row.id, provider=provider(),
                recipient_id=application.owner_id, application_id=application.id, reminder_id=row.id,
                text=f"招聘提醒：{application.application_code} {label}。请在Web核对处理。")
            db.add(notice)
            record_change(db, notice, actor, "queue_notification")
            count += 1

        apps = db.scalars(select(Application).join(User, User.id == Application.owner_id).where(
            Application.deleted_at.is_(None), Application.stage.not_in(TERMINAL),
            User.active.is_(True), User.deleted_at.is_(None), User.role.in_(["ADMIN", "HR"])).execution_options(yield_per=100))
        for application in apps:
            interviews = db.scalars(select(Interview).where(Interview.application_id == application.id,
                Interview.deleted_at.is_(None), Interview.status == "scheduled", Interview.scheduled_at.is_not(None)))
            for interview in interviews:
                when = interview.scheduled_at
                if when is None:
                    continue
                if now < when <= now + timedelta(hours=settings.interview_hours):
                    queue(application, "interview", interview.id, when, when - timedelta(hours=settings.interview_hours), "面试即将开始")
                elif when <= now - timedelta(hours=settings.feedback_hours):
                    queue(application, "feedback", interview.id, when, when + timedelta(hours=settings.feedback_hours), "面试反馈超时")
            if application.updated_at <= now - timedelta(days=settings.stalled_days):
                queue(application, "stalled", application.id, application.updated_at,
                    application.updated_at + timedelta(days=settings.stalled_days), "进度停滞")
            job = latest_sync(db, application.id)
            if job and job.status in {"failed", "dead"}:
                queue(application, "sync", job.id, job.created_at, job.created_at, "最新协作表同步异常")
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # competing scanner already queued the unique facts
            return 0
        return count


def notification_read(db, row):
    user = db.get(User, row.recipient_id)
    return s.NotificationRead(**{key: getattr(row, key) for key in (
        "id", "version", "created_at", "updated_at", "provider", "status", "application_id", "text",
        "attempts", "last_error", "platform_message_id", "completed_at")},
        recipient_name=user.display_name if user else "已停用用户")


def authorized_recipient(db, row):
    user = db.get(User, row.recipient_id)
    if not user or not user.active or user.deleted_at or user.role not in {"ADMIN", "HR"}:
        return None
    if row.application_id:
        application = get_entity(db, Application, row.application_id, user)
        if row.reminder_id:
            reminder = db.get(Reminder, row.reminder_id)
            if application.stage in TERMINAL or not reminder or not fact_valid(db, reminder, application, policy(db), utcnow()):
                return None
    return user


def finish(db, row, state, error=None, message_id=None):
    actor = db.get(User, SYNC_ACTOR_ID)
    before = snapshot(row)
    retry_at = utcnow() + timedelta(seconds=5 * 2 ** (row.attempts - 1)) if error == "TOKEN_UNAVAILABLE" and row.attempts < 3 else None
    conditional_update(db, row, row.version, {"status": state, "last_error": error,
        "platform_message_id": message_id, "processing_token": None, "lease_expires_at": None,
        "next_retry_at": retry_at, "completed_at": utcnow() if state in {"accepted", "mock_sent", "cancelled"} else None})
    record_change(db, row, actor, "finish_notification", before)
    if row.reminder_id:
        reminder = db.get(Reminder, row.reminder_id)
        before = snapshot(reminder)
        conditional_update(db, reminder, reminder.version, {"status": state,
            "sent_at": utcnow() if state == "accepted" else None})
        record_change(db, reminder, actor, "finish_reminder", before)


def claim_notification():
    with SessionLocal() as db:
        expired = db.scalars(select(Notification).where(Notification.status == "processing",
            Notification.lease_expires_at <= utcnow())).all()
        for row in expired:
            finish(db, row, "pending" if row.provider == "mock" else "uncertain", "CLAIM_EXPIRED")
        db.commit()
        row = db.scalar(select(Notification).where(or_(Notification.status == "pending",
            (Notification.status == "failed") & (Notification.next_retry_at <= utcnow())))
            .order_by(Notification.created_at).limit(1))
        if row is None:
            return None
        try:
            user = authorized_recipient(db, row)
        except BusinessError:
            user = None
        if user is None:
            finish(db, row, "cancelled", "FACT_OR_PERMISSION_CHANGED")
            db.commit()
            return ()
        token = new_id()
        before = snapshot(row)
        conditional_update(db, row, row.version, {"status": "processing", "attempts": row.attempts + 1,
            "processing_token": token, "lease_expires_at": utcnow() + timedelta(seconds=120)})
        actor = db.get(User, SYNC_ACTOR_ID)
        assert actor is not None, "System actor missing"
        record_change(db, row, actor, "claim_notification", before)
        db.commit()
        return row.id, token, row.provider, user.external_wecom_userid, row.text


async def process_notification(adapter=None):
    claim = claim_notification()
    if claim is None:
        return False
    if not claim:
        return True
    task_id, token, mode, recipient, text = claim
    try:
        result = await (adapter or sender).send(mode, recipient, text, task_id)
    except Exception:
        result = SendResult("uncertain", "SEND_RESULT_UNKNOWN")
    with SessionLocal() as db:
        row = db.get(Notification, task_id)
        if row and row.status == "processing" and row.processing_token == token:
            finish(db, row, result.state, result.error, result.message_id)
            db.commit()
    return True


def retry_notification(db, actor, row, expected, reason):
    if row.status not in {"failed", "blocked"}:
        fail(409, "INVALID_TASK_STATE", "仅明确失败/待配置任务可重试；结果不明须先人工核实，禁止盲目重发")
    if authorized_recipient(db, row) is None:
        fail(409, "STALE_NOTIFICATION", "原事实或接收人权限已变更")
    before = snapshot(row)
    conditional_update(db, row, expected, {"status": "pending", "next_retry_at": None, "last_error": None})
    record_change(db, row, actor, "retry_notification", before, reason)
    return notification_read(db, row)
