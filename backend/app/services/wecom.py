"""Durable receive/claim/ingest/finish, preserving the S2 business transaction boundary."""

import hashlib
import os
from datetime import timedelta

from sqlalchemy import delete, or_, select

from app import schemas as s
from app.core.errors import BusinessError
from app.core.security import SYNC_ACTOR_ID, require_writer
from app.db import Notification, SessionLocal, User, WecomInbox, WecomReplay, new_id, utcnow
from app.integrations.parsers.factory import get_parser
from app.integrations.parsers.privacy import redact
from app.integrations.wecom.callback import xml_fields
from app.services.common import conditional_update, fail, record_change, snapshot
from app.services.ingestion import active_actor, ingest


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def inbox_read(row):
    return s.InboxRead.model_validate(row)


def receive(db, actor, provider: str, message_id: str, text: str):
    require_writer(actor)
    event_key = digest(f"{provider}:{os.getenv('WECOM_CORP_ID', '') if provider == 'wecom' else actor.id}:"
                       f"{os.getenv('WECOM_AGENT_ID', '') if provider == 'wecom' else ''}:{message_id}")
    message_hash = digest(text)
    old = db.scalar(select(WecomInbox).where(WecomInbox.event_key == event_key))
    if old:
        if old.actor_id != actor.id or old.message_hash != message_hash:
            fail(409, "IDEMPOTENCY_CONFLICT", "相同消息ID的发送人或内容已改变")
        return inbox_read(old)
    row = WecomInbox(event_key=event_key, provider=provider, actor_id=actor.id,
        message_hash=message_hash, safe_text=redact(text))
    db.add(row)
    record_change(db, row, actor, "receive_wecom", source=provider)
    return inbox_read(row)


def receive_callback(db, plaintext: bytes, timestamp: str, nonce: str, encrypted: str):
    fields = xml_fields(plaintext)
    if fields.get("ToUserName") != os.environ["WECOM_CORP_ID"] or fields.get("AgentID") != os.environ["WECOM_AGENT_ID"]:
        fail(403, "INVALID_RECEIVER", "回调企业或应用标识不匹配")
    replay_key = digest(timestamp + ":" + nonce)
    payload_hash = digest(encrypted)
    db.execute(delete(WecomReplay).where(WecomReplay.expires_at < utcnow()))
    replay = db.get(WecomReplay, replay_key)
    if replay and replay.payload_hash != payload_hash:
        fail(403, "REPLAY_CONFLICT", "签名随机数已用于其他内容")
    if not replay:
        db.add(WecomReplay(id=replay_key, payload_hash=payload_hash, expires_at=utcnow() + timedelta(minutes=10)))
    if fields.get("MsgType") != "text":
        return  # authenticated unsupported events are ACKed without ingestion
    actor = db.scalar(select(User).where(User.external_wecom_userid == fields.get("FromUserName"),
        User.active.is_(True), User.deleted_at.is_(None)))
    if actor is None:
        fail(403, "SENDER_NOT_BOUND", "发送人尚未绑定有效内部用户")
    req = s.MockMessage(message_id=fields.get("MsgId", ""), text=fields.get("Content", ""))
    receive(db, actor, "wecom", req.message_id, req.text)


def claim_inbox():
    with SessionLocal() as db:
        row = db.scalar(select(WecomInbox).where(or_(
            (WecomInbox.status == "pending") & (WecomInbox.next_retry_at.is_(None) | (WecomInbox.next_retry_at <= utcnow())),
            (WecomInbox.status == "processing") & (WecomInbox.lease_expires_at <= utcnow()),
        )).order_by(WecomInbox.created_at).limit(1))
        if row is None:
            return None
        actor = db.get(User, SYNC_ACTOR_ID)
        assert actor is not None, "System actor missing"
        before = snapshot(row)
        token = new_id()
        conditional_update(db, row, row.version, {"status": "processing", "processing_token": token,
            "attempts": row.attempts + 1, "lease_expires_at": utcnow() + timedelta(seconds=150)})
        record_change(db, row, actor, "claim_wecom", before)
        db.commit()
        return row.id, token, row.actor_id, row.provider, row.event_key, row.safe_text, row.created_at


async def process_inbox():
    claim = claim_inbox()
    if claim is None:
        return False
    row_id, token, actor_id, provider, event_key, text, reference_time = claim
    error = None
    result = None
    try:
        result = await ingest(actor_id, s.IngestionRequest(text=text or "", source="wecom" if provider == "wecom" else "wecom_mock",
            external_event_id="inbox:" + event_key), get_parser(), reference_time=reference_time)
    except BusinessError as exc:
        error = "ACTOR_FORBIDDEN" if exc.status == 403 else "INGESTION_CONFLICT"
    except Exception:
        error = "INGESTION_FAILED"
    with SessionLocal() as db:
        row = db.get(WecomInbox, row_id)
        if not row or row.processing_token != token or row.status != "processing":
            return True
        actor = db.get(User, SYNC_ACTOR_ID)
        assert actor is not None, "System actor missing"
        before = snapshot(row)
        pending = result is not None and result.status == "parsing"
        values = {"status": "pending" if pending else "failed" if error else "completed",
            "processing_token": None, "lease_expires_at": None, "last_error": error,
            "next_retry_at": utcnow() + timedelta(seconds=125) if pending else None}
        if result:
            values["ingestion_id"] = result.ingestion_id
        if not pending and not error:
            values["safe_text"] = None  # drop even the redacted work payload once finished
            message = "招聘消息已处理，请在Web查看记录。" if result and result.status in {"applied", "duplicate"} else "招聘消息需要人工核对，请在Web查看AI审核队列。"
            notice = Notification(dedupe_key="inbox:" + row.id, provider=row.provider, recipient_id=row.actor_id,
                application_id=result.application_id if result else None, text=message)
            db.add(notice)
            record_change(db, notice, actor, "queue_notification")
        conditional_update(db, row, row.version, values)
        record_change(db, row, actor, "finish_wecom", before)
        db.commit()
    return True


def retry_inbox(db, actor, row, expected, reason):
    if row.status != "failed" or row.safe_text is None:
        fail(409, "INVALID_TASK_STATE", "仅失败且仍保留待处理摘要的任务可以重试")
    active_actor(db, row.actor_id)
    before = snapshot(row)
    conditional_update(db, row, expected, {"status": "pending", "last_error": None, "next_retry_at": None})
    record_change(db, row, actor, "retry_wecom", before, reason)
    return inbox_read(row)


def binding(db, actor, user, req, expected):
    if user.id == SYNC_ACTOR_ID or not user.active or user.deleted_at:
        fail(400, "INVALID_USER", "不能绑定系统或停用用户")
    if req.external_userid == "@all":
        fail(400, "INVALID_USER", "不允许广播接收者")
    before = snapshot(user)
    conditional_update(db, user, expected, {"external_wecom_userid": req.external_userid})
    record_change(db, user, actor, "bind_wecom_user", before, req.change_reason)
    return s.WecomUser.model_validate(user)
