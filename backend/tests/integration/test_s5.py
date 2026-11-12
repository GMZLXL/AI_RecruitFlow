import asyncio
import base64
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import TypeVar

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool
from wechatpy.enterprise.crypto import WeChatCrypto

from app.core.security import DEV_IDS
from app.db import (
    Application,
    AuditLog,
    IngestionJob,
    Interview,
    Notification,
    Outbox,
    Reminder,
    SessionLocal,
    User,
    WecomInbox,
    utcnow,
)
from app.integrations.wecom.callback import xml_fields
from app.integrations.wecom.sender import SendResult
from app.services import notifications as notices
from app.services import wecom
from tests.helpers import create, headers, setup_owned_application

BASE = "/api/v1"
CORP, AGENT, TOKEN = "synthetic-corp", "1000001", "synthetic-callback-token"
AES_KEY = base64.b64encode(bytes(range(32))).decode()[:-1]
T = TypeVar("T")


def required(db: Session, model: type[T], key: str) -> T:
    obj = db.get(model, key)
    assert obj is not None
    return obj


def configure(monkeypatch):
    for key, value in {"APP_MODE": "hybrid", "WECOM_PROVIDER": "wecom", "WECOM_CALLBACK_ENABLED": "true",
        "WECOM_CORP_ID": CORP, "WECOM_AGENT_ID": AGENT, "WECOM_CALLBACK_TOKEN": TOKEN,
        "WECOM_ENCODING_AES_KEY": AES_KEY}.items():
        monkeypatch.setenv(key, value)


def encrypted(text, nonce="synthetic-nonce", timestamp=None, corp=CORP):
    stamp = str(timestamp or int(time.time()))
    raw = WeChatCrypto(TOKEN, AES_KEY, corp).encrypt_message(text, nonce, stamp)
    fields = xml_fields(raw)
    return raw, {"msg_signature": fields["MsgSignature"], "timestamp": stamp, "nonce": nonce}, fields["Encrypt"]


def xml(message_id="synthetic-msg-1", text="A10001进入筛选", sender="synthetic-hr", agent=AGENT, corp=CORP, kind="text"):
    return f"<xml><ToUserName>{corp}</ToUserName><FromUserName>{sender}</FromUserName><AgentID>{agent}</AgentID><MsgType>{kind}</MsgType><MsgId>{message_id}</MsgId><Content>{text}</Content></xml>"


def bind(client, user="hr-a"):
    with SessionLocal() as db:
        row = required(db, User, DEV_IDS[user])
        version = row.version
    result = client.patch(BASE + "/wecom/users/" + DEV_IDS[user], headers=headers(version=version),
        json={"external_userid": "synthetic-hr", "change_reason": "虚构协议测试绑定"})
    assert result.status_code == 200, result.text


def mock(client, text="A10001进入筛选", msgid="mock-event", user="admin", key=None):
    return client.post(BASE + "/wecom/mock/messages", headers=headers(user, key=key),
        json={"message_id": msgid, "text": text})


def enable_reminders(client):
    policy = client.get(BASE + "/settings/reminders").json()["data"]
    data = {key: policy[key] for key in ("enabled", "interview_hours", "feedback_hours", "stalled_days")}
    data.update(enabled=True, change_reason="虚构提醒测试")
    response = client.patch(BASE + "/settings/reminders", headers=headers(version=policy["version"]), json=data)
    assert response.status_code == 200, response.text
    return response


def test_mock_durable_ack_pipeline_dedup_and_minimal_notice(client):
    application = create(client).json()["data"]
    text = "A10001进入筛选 联系人13800138000 邮箱synthetic@example.test"
    first = mock(client, text)
    assert first.status_code == 202 and first.json()["data"]["status"] == "pending"
    task_id = first.json()["data"]["id"]
    for _ in range(2):
        assert mock(client, text).json()["data"]["id"] == task_id
    assert mock(client, "另一条消息").status_code == 409
    with SessionLocal() as db:
        row = required(db, WecomInbox, task_id)
        assert row.safe_text is not None
        assert "13800138000" not in row.safe_text and "synthetic@example.test" not in row.safe_text
        assert required(db, Application, application["id"]).version == 1  # no parsing on callback path
    assert asyncio.run(wecom.process_inbox())
    assert not asyncio.run(wecom.process_inbox())
    with SessionLocal() as db:
        row = required(db, WecomInbox, task_id)
        assert row.status == "completed" and row.safe_text is None and row.ingestion_id
        assert db.scalar(select(func.count(IngestionJob.id))) == 1
        assert required(db, Application, application["id"]).stage == "screening"
        assert db.scalar(select(func.count(Notification.id))) == 1
        assert not any("13800138000" in str(log.metadata_json) for log in db.scalars(select(AuditLog)))
    assert asyncio.run(notices.process_notification())
    assert not asyncio.run(notices.process_notification())
    notification = client.get(BASE + "/notifications").json()["data"][0]
    assert notification["status"] == "mock_sent" and notification["platform_message_id"].startswith("MOCK-NOTICE-")
    assert "虚构候选甲" not in notification["text"]
    assert mock(client, text).json()["data"]["id"] == task_id


def test_verified_get_echo_post_ack_and_replay(client, monkeypatch):
    configure(monkeypatch)
    application, _, _ = setup_owned_application(client)
    bind(client)
    _, params, echo = encrypted("synthetic-echo")
    response = client.get(BASE + "/webhooks/wecom", params={**params, "echostr": echo})
    assert response.status_code == 200 and response.content == b"synthetic-echo"
    raw, params, _ = encrypted(xml(), nonce="post-nonce")
    for _ in range(3):
        response = client.post(BASE + "/webhooks/wecom", params=params, content=raw)
        assert response.status_code == 200 and response.text == "success", response.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count(WecomInbox.id))) == 1
        assert required(db, Application, application["id"]).stage == "applied"
    assert asyncio.run(wecom.process_inbox())
    with SessionLocal() as db:
        assert required(db, Application, application["id"]).stage == "screening"
        assert db.scalar(select(IngestionJob.source)) == "wecom"
    # Sending is independently disabled; no synthetic success or network fallback.
    assert asyncio.run(notices.process_notification())
    assert client.get(BASE + "/notifications").json()["data"][0]["status"] == "blocked"
    assert client.post(BASE + "/ingestions", json={"text": "test", "source": "wecom"}).status_code == 403


@pytest.mark.parametrize("failure", ["signature", "expired", "future", "nonce", "corpid", "agent", "sender", "duplicate_field", "dtd", "oversize"])
def test_invalid_callbacks_never_enqueue(client, monkeypatch, failure):
    configure(monkeypatch)
    bind(client)
    text = xml(agent="different" if failure == "agent" else AGENT,
        sender="unknown" if failure == "sender" else "synthetic-hr")
    if failure == "duplicate_field":
        text = text.replace("</xml>", "<MsgId>ambiguous</MsgId></xml>")
    if failure == "dtd":
        text = '<!DOCTYPE xml [<!ENTITY injected "test">]>' + text
    stamp = int(time.time()) + (900 if failure == "future" else -900 if failure == "expired" else 0)
    raw, params, _ = encrypted(text, timestamp=stamp, corp="another-corp" if failure == "corpid" else CORP)
    if failure == "signature":
        params["msg_signature"] = "0" * 40
    if failure == "nonce":
        params["nonce"] = "different-nonce"
    if failure == "oversize":
        raw = b"x" * 65537
    response = client.post(BASE + "/webhooks/wecom", params=params, content=raw)
    assert response.status_code in {400, 403, 413}, response.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count(WecomInbox.id))) == 0
        assert db.scalar(select(func.count(IngestionJob.id))) == 0


def test_nonce_conflict_unsupported_events_and_missing_config(client, monkeypatch):
    response = client.get(BASE + "/webhooks/wecom", params={"msg_signature": "0" * 40, "timestamp": str(int(time.time())), "nonce": "x", "echostr": "test"})
    assert response.status_code == 503
    configure(monkeypatch)
    raw, params, _ = encrypted(xml(kind="event"))
    assert client.post(BASE + "/webhooks/wecom", params=params, content=raw).text == "success"
    raw2, _, _ = encrypted(xml(kind="image"), timestamp=int(params["timestamp"]))
    fields = xml_fields(raw2)
    params["msg_signature"] = fields["MsgSignature"]
    assert client.post(BASE + "/webhooks/wecom", params=params, content=raw2).status_code == 403


def test_bind_policy_permissions_versions_and_replay(client):
    bind(client)
    with SessionLocal() as db:
        user = required(db, User, DEV_IDS["hr-a"])
        version = user.version
    data = {"external_userid": "synthetic-new", "change_reason": "虚构绑定更新"}
    h = headers(version=version)
    path = BASE + "/wecom/users/" + DEV_IDS["hr-a"]
    assert client.patch(path, json=data, headers=h).status_code == 200
    assert client.patch(path, json=data, headers=h).status_code == 200
    assert client.patch(path, json=data, headers=headers(version=version)).status_code == 409
    for path in ("/wecom/status", "/wecom/users", "/settings/reminders"):
        assert client.get(BASE + path, headers=headers("hr-a")).status_code == 403
    assert mock(client, user="manager-a").status_code == 403
    assert client.post(BASE + "/wecom/mock/messages", json={"message_id": "x", "text": "test"}).status_code == 400
    current = enable_reminders(client).json()["data"]
    assert current["enabled"] and current["version"] == 2


def test_worker_rechecks_actor_permission_and_failed_inbox_retry(client):
    mock(client, user="hr-a")
    with SessionLocal() as db:
        user = required(db, User, DEV_IDS["hr-a"])
        user.active = False
        db.commit()
    assert asyncio.run(wecom.process_inbox())
    row = client.get(BASE + "/wecom/inbox").json()["data"][0]
    assert row["status"] == "failed" and row["last_error"] == "ACTOR_FORBIDDEN"
    path = BASE + "/wecom/inbox/" + row["id"] + "/retry"
    assert client.post(path, headers=headers(version=row["version"]), json={"change_reason": "虚构重试"}).status_code == 403
    with SessionLocal() as db:
        user = required(db, User, DEV_IDS["hr-a"])
        user.active = True
        db.commit()
    assert client.post(path, headers=headers(version=row["version"]), json={"change_reason": "虚构权限恢复"}).status_code == 200
    assert asyncio.run(wecom.process_inbox())


def test_receive_atomic_audit_outbox_rollback(client):
    def broken(*_):
        raise RuntimeError("synthetic audit failure")
    event.listen(Outbox, "before_insert", broken)
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as isolated:
            assert mock(isolated).status_code == 500
    finally:
        event.remove(Outbox, "before_insert", broken)
    with SessionLocal() as db:
        assert db.scalar(select(func.count(WecomInbox.id))) == 0
        assert db.scalar(select(func.count(AuditLog.id))) == 0


def reminder_fixture(client):
    application, _, _ = setup_owned_application(client)
    with SessionLocal() as db:
        obj = required(db, Application, application["id"])
        obj.updated_at = utcnow() - timedelta(days=10)
        future = Interview(application_id=obj.id, round=1, scheduled_at=utcnow() + timedelta(hours=2), interviewer="虚构面试官")
        past = Interview(application_id=obj.id, round=2, scheduled_at=utcnow() - timedelta(hours=30), interviewer="虚构面试官")
        db.add_all([future, past])
        job = db.scalar(select(Outbox).where(Outbox.entity_type == "applications", Outbox.entity_id == obj.id))
        assert job is not None
        job.status = "dead"
        db.commit()
    enable_reminders(client)
    return application


def test_reminders_four_facts_dedup_mock_delivery_scope_and_cancel(client):
    application = reminder_fixture(client)
    assert notices.generate_reminders() == 4
    assert notices.generate_reminders() == 0
    with SessionLocal() as db:
        assert {r.reminder_type for r in db.scalars(select(Reminder))} == {"interview", "feedback", "stalled", "sync"}
    assert client.get(BASE + "/notifications", headers=headers("hr-b")).json()["data"] == []
    assert client.get(BASE + "/notifications", headers=headers("manager-a")).json()["data"] == []
    assert len(client.get(BASE + "/notifications", headers=headers("hr-a")).json()["data"]) == 4
    # Facts change after generation: no stale notification is delivered.
    with SessionLocal() as db:
        for interview in db.scalars(select(Interview)):
            interview.status = "completed"
            interview.result = "passed"
        obj = required(db, Application, application["id"])
        obj.updated_at = utcnow()
        for job in db.scalars(select(Outbox)):
            job.status = "mock_synced"
        db.commit()
    while asyncio.run(notices.process_notification()):
        pass
    with SessionLocal() as db:
        assert {n.status for n in db.scalars(select(Notification))} == {"cancelled"}


def test_notification_crash_uncertain_and_retry_state_version(client):
    reminder_fixture(client)
    notices.generate_reminders()
    with SessionLocal() as db:
        first = db.scalar(select(Notification))
        assert first is not None
        first.provider = "wecom"
        first.status = "processing"
        first.processing_token = str(uuid.uuid4())
        first.lease_expires_at = utcnow() - timedelta(seconds=1)
        target_id = first.id
        db.commit()
    # Expired real send becomes uncertain and is never selected for automatic resending.
    notices.claim_notification()
    with SessionLocal() as db:
        target = required(db, Notification, target_id)
        assert target.status == "uncertain"
        version = target.version
    response = client.post(BASE + "/notifications/" + target_id + "/retry", headers=headers(version=version), json={"change_reason": "虚构核实"})
    assert response.status_code == 409


def test_delivery_no_transaction_and_fenced_finalization(client):
    create(client)
    mock(client)
    asyncio.run(wecom.process_inbox())

    class Adapter:
        async def send(self, provider, recipient, text, task_id):
            from app.db import engine

            assert isinstance(engine.pool, QueuePool) and engine.pool.checkedout() == 0
            with SessionLocal() as db:
                row = required(db, Notification, task_id)
                row.processing_token = "another-worker-token"
                row.status = "uncertain"
                db.commit()
            return SendResult("accepted", message_id="synthetic-message-id")

    asyncio.run(notices.process_notification(Adapter()))
    row = client.get(BASE + "/notifications").json()["data"][0]
    assert row["status"] == "uncertain" and row["platform_message_id"] is None


def test_delayed_processing_preserves_original_receive_time(client):
    create(client)
    task = mock(client).json()["data"]
    with SessionLocal() as db:
        row = required(db, WecomInbox, task["id"])
        received = utcnow() - timedelta(days=2)
        row.created_at = received
        db.commit()
    asyncio.run(wecom.process_inbox())
    with SessionLocal() as db:
        ingestion = db.scalar(select(IngestionJob))
        assert ingestion is not None and ingestion.received_at == received


def test_concurrent_callback_delivery_enqueues_once(client, monkeypatch):
    configure(monkeypatch)
    bind(client)
    raw, params, _ = encrypted(xml())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(BASE + "/webhooks/wecom", params=params, content=raw), range(2)))
    assert all(response.status_code == 200 for response in responses)
    with SessionLocal() as db:
        assert db.scalar(select(func.count(WecomInbox.id))) == 1
