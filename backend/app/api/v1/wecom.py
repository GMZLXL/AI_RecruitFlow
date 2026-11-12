import os
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import schemas as s
from app.core.security import SYNC_ACTOR_ID, require_admin
from app.db import Application, Notification, User, WecomInbox
from app.domain import Role
from app.integrations.wecom.callback import decrypt, xml_fields
from app.integrations.wecom.config import status
from app.services import notifications as notice
from app.services import wecom as svc
from app.services.common import fail, mutate, visibility

from .common import DB, Actor, Key, Page, PageSize, Version, envelope, listing

router = APIRouter()
Signature = Annotated[str, Query(min_length=40, max_length=40)]
Timestamp = Annotated[str, Query(min_length=1, max_length=12)]
Nonce = Annotated[str, Query(min_length=1, max_length=128)]


@router.get("/webhooks/wecom", response_class=PlainTextResponse)
def verify_url(msg_signature: Signature, timestamp: Timestamp, nonce: Nonce,
    echostr: Annotated[str, Query(min_length=1, max_length=65536)]):
    return PlainTextResponse(decrypt(msg_signature, timestamp, nonce, echostr))


@router.post("/webhooks/wecom", response_class=PlainTextResponse,
    openapi_extra={"requestBody": {"required": True, "content": {"application/xml": {"schema": {"type": "string", "maxLength": 65536}}}}})
async def callback(request: Request, db: DB, msg_signature: Signature, timestamp: Timestamp, nonce: Nonce):
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > 65536:
            fail(413, "CALLBACK_TOO_LARGE", "回调内容过大")
    encrypted = xml_fields(bytes(chunks)).get("Encrypt", "")
    plaintext = decrypt(msg_signature, timestamp, nonce, encrypted)
    for attempt in range(2):
        try:
            svc.receive_callback(db, plaintext, timestamp, nonce, encrypted)
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if attempt:
                fail(409, "EVENT_IN_PROGRESS", "消息已被并发接收，请重试原回调")
        except ValidationError:
            db.rollback()
            fail(400, "INVALID_CALLBACK_MESSAGE", "消息缺少有效ID或文本（最多2000字）")
    request.app.state.wecom_wakeup.set()
    return PlainTextResponse("success")


@router.get("/wecom/status", response_model=s.Response[s.WecomStatus])
def wecom_status(request: Request, actor: Actor):
    require_admin(actor)
    return envelope(request, status())


@router.post("/wecom/mock/messages", response_model=s.Response[s.InboxRead], status_code=202)
def mock_message(data: s.MockMessage, request: Request, db: DB, actor: Actor, key: Key = None):
    if os.getenv("APP_ENV", "development") != "development" or status().provider != "mock":
        fail(403, "MOCK_DISABLED", "模拟投稿仅在开发Mock企微模式可用")
    result = mutate(db, actor, "mock_wecom", key, data.model_dump(mode="json"),
        lambda: svc.receive(db, actor, "mock", data.message_id, data.text))
    request.app.state.wecom_wakeup.set()
    return envelope(request, result)


@router.get("/wecom/inbox", response_model=s.ListResponse[s.InboxRead])
def inbox(request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20):
    query = select(WecomInbox).where(WecomInbox.deleted_at.is_(None))
    if actor.role != Role.ADMIN:
        query = query.where(WecomInbox.actor_id == actor.id)
    return listing(request, db, query.order_by(WecomInbox.created_at.desc(), WecomInbox.id), page, page_size, svc.inbox_read)


@router.post("/wecom/inbox/{task_id}/retry", response_model=s.Response[s.InboxRead])
def retry_inbox(task_id: s.Id, data: s.TaskRetry, request: Request, db: DB, actor: Actor, expected: Version, key: Key = None):
    require_admin(actor)
    row = db.get(WecomInbox, task_id)
    if row is None:
        fail(404, "NOT_FOUND", "接收任务不存在")
    result = mutate(db, actor, "retry_wecom:" + task_id, key, {**data.model_dump(), "version": expected},
        lambda: svc.retry_inbox(db, actor, row, expected, data.change_reason))
    request.app.state.wecom_wakeup.set()
    return envelope(request, result)


@router.get("/notifications", response_model=s.ListResponse[s.NotificationRead])
def notifications(request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20):
    query = select(Notification).where(Notification.deleted_at.is_(None))
    if actor.role != Role.ADMIN:
        query = query.where(Notification.recipient_id == actor.id,
            Notification.application_id.is_(None) | Notification.application_id.in_(
                select(Application.id).where(visibility(Application, actor))))
    return listing(request, db, query.order_by(Notification.created_at.desc(), Notification.id), page, page_size,
        lambda row: notice.notification_read(db, row))


@router.post("/notifications/{task_id}/retry", response_model=s.Response[s.NotificationRead])
def retry_notification(task_id: s.Id, data: s.TaskRetry, request: Request, db: DB, actor: Actor, expected: Version, key: Key = None):
    require_admin(actor)
    row = db.get(Notification, task_id)
    if row is None:
        fail(404, "NOT_FOUND", "通知不存在")
    result = mutate(db, actor, "retry_notice:" + task_id, key, {**data.model_dump(), "version": expected},
        lambda: notice.retry_notification(db, actor, row, expected, data.change_reason))
    request.app.state.wecom_wakeup.set()
    return envelope(request, result)


@router.get("/settings/reminders", response_model=s.Response[s.ReminderPolicyRead])
def reminder_policy(request: Request, db: DB, actor: Actor):
    require_admin(actor)
    row = notice.policy(db)
    db.commit()
    return envelope(request, s.ReminderPolicyRead.model_validate(row))


@router.patch("/settings/reminders", response_model=s.Response[s.ReminderPolicyRead])
def reminder_policy_update(data: s.ReminderPolicyUpdate, request: Request, db: DB, actor: Actor, expected: Version, key: Key = None):
    require_admin(actor)
    result = mutate(db, actor, "update_reminders", key, {**data.model_dump(), "version": expected},
        lambda: notice.update_policy(db, actor, data, expected))
    request.app.state.wecom_wakeup.set()
    return envelope(request, result)


@router.get("/wecom/users", response_model=s.ListResponse[s.WecomUser])
def users(request: Request, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 20):
    require_admin(actor)
    query = select(User).where(User.id != SYNC_ACTOR_ID, User.active.is_(True), User.deleted_at.is_(None))
    return listing(request, db, query.order_by(User.display_name, User.id), page, page_size, s.WecomUser.model_validate)


@router.patch("/wecom/users/{user_id}", response_model=s.Response[s.WecomUser])
def bind_user(user_id: s.Id, data: s.WecomBinding, request: Request, db: DB, actor: Actor, expected: Version, key: Key = None):
    require_admin(actor)
    user = db.get(User, user_id)
    if user is None:
        fail(404, "NOT_FOUND", "用户不存在")
    return envelope(request, mutate(db, actor, "bind_wecom:" + user_id, key,
        {**data.model_dump(), "version": expected}, lambda: svc.binding(db, actor, user, data, expected)))
