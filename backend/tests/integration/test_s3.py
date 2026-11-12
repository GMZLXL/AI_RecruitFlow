import asyncio
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.db import (
    AuditLog,
    MockSheetRecord,
    Outbox,
    RemoteLink,
    SessionLocal,
    SyncWorkerLease,
    engine,
    utcnow,
)
from app.integrations.smartsheet.base import SheetError
from app.integrations.smartsheet.mock import MockSmartSheetAdapter
from app.main import app
from app.services import sync
from tests.helpers import create, headers


def drain(**kwargs):
    return asyncio.run(sync.process_batch(**kwargs))


def app_job(client, app_id):
    return next(
        row
        for row in client.get("/api/v1/sync/jobs", params={"application_id": app_id}).json()["data"]
        if row["entity_type"] == "applications"
    )


def test_async_dispatch_update_mapping_and_persistent_remote(client):
    obj = create(client).json()["data"]
    key = headers()
    response = client.post("/api/v1/sync/run", headers=key)
    assert response.status_code == 202 and response.json()["data"]["accepted"]
    assert client.post("/api/v1/sync/run", headers=key).json()["data"] == response.json()["data"]
    assert app_job(client, obj["id"])["status"] == "pending"
    assert drain() == 3
    first = app_job(client, obj["id"])
    assert first["status"] == "mock_synced" and first["mode"] == "mock"
    assert first["completed_at"].endswith("Z")
    assert first["attempts"] == first["cycle_attempts"] == 1
    assert (
        client.patch(
            f"/api/v1/applications/{obj['id']}",
            headers=headers(version=1),
            json={"stage": "screening", "change_reason": "虚构同步更新"},
        ).status_code
        == 200
    )
    assert drain() == 1
    current = app_job(client, obj["id"])
    assert current["remote_record_id"] == first["remote_record_id"]
    records = asyncio.run(MockSmartSheetAdapter().list_remote_records())
    assert len(records) == 1 and records[0].version == 2 and records[0].stage == "screening"
    assert drain() == 0
    summary = client.get("/api/v1/sync/summary").json()["data"]
    assert summary["counts"]["mock_synced"] == 4
    assert summary["last_success_at"] is not None
    assert summary["tencent_docs"] == "blocked_by_credentials"
    with SessionLocal() as db:
        assert db.scalar(select(func.count(RemoteLink.id))) == 1
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "request_sync_run")) == 1


def test_remote_failure_keeps_business_and_exponential_dead_letter(client, monkeypatch):
    obj = create(client).json()["data"]
    monkeypatch.setenv("MOCK_SHEET_FAILURE", "timeout")
    now = utcnow()
    assert drain(now=now) == 3
    for cycle, delay in enumerate((5, 10, 20, 40), start=1):
        row = app_job(client, obj["id"])
        assert row["status"] == "failed" and row["cycle_attempts"] == cycle
        from datetime import datetime

        due = datetime.fromisoformat(row["next_retry_at"].replace("Z", "+00:00"))
        assert (due - now).total_seconds() == delay
        assert drain(now=due - timedelta(microseconds=1)) == 0
        now = due
        drain(now=now)
    dead = app_job(client, obj["id"])
    assert dead["status"] == "dead" and dead["attempts"] == 5
    assert dead["next_retry_at"] is None and dead["last_error"] == "REMOTE_TIMEOUT"
    assert client.get(f"/api/v1/applications/{obj['id']}").json()["data"]["version"] == 1
    assert client.get("/api/v1/dashboard/overview").json()["data"]["pending_sync"] == 1
    assert drain(now=now + timedelta(days=1)) == 0


def test_admin_retry_rbac_revision_idempotency_and_recovery(client, monkeypatch):
    obj = create(client).json()["data"]
    monkeypatch.setenv("MOCK_SHEET_FAILURE", "permission")
    drain()
    row = app_job(client, obj["id"])
    path = f"/api/v1/sync/jobs/{row['id']}/retry"
    body = {"reason": "虚构权限恢复后重试"}
    assert row["status"] == "dead" and row["attempts"] == 1
    assert client.post(path, headers=headers("hr-a", row["revision"]), json=body).status_code == 403
    assert client.post(path, headers=headers(version=row["revision"] - 1), json=body).status_code == 409
    assert (
        client.post(path, headers=headers(version=row["revision"]), json={"reason": " "}).status_code == 422
    )
    key = headers(version=row["revision"])
    assert client.post(path, headers={"If-Match": str(row["revision"])}, json=body).status_code == 400
    response = client.post(path, headers=key, json=body)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    assert response.json()["data"]["cycle_attempts"] == 0
    assert client.post(path, headers=key, json=body).json()["data"] == response.json()["data"]
    assert client.post(path, headers=key, json={"reason": "不同请求"}).status_code == 409
    monkeypatch.setenv("MOCK_SHEET_FAILURE", "none")
    drain()
    assert app_job(client, obj["id"])["status"] == "mock_synced"
    assert (
        client.post(
            path, headers=headers(version=app_job(client, obj["id"])["revision"]), json=body
        ).status_code
        == 409
    )
    with SessionLocal() as db:
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "retry_sync")) == 1


def test_remote_success_before_local_ack_is_idempotently_recovered(client, monkeypatch):
    obj = create(client).json()["data"]
    monkeypatch.setenv("MOCK_SHEET_FAILURE", "after_write_timeout")
    now = utcnow()
    drain(now=now)
    assert app_job(client, obj["id"])["status"] == "failed"
    with SessionLocal() as db:
        record = db.get(MockSheetRecord, obj["id"])
        assert record is not None
        first_id = record.remote_record_id
        assert db.scalar(select(func.count(RemoteLink.id))) == 0
    monkeypatch.setenv("MOCK_SHEET_FAILURE", "none")
    drain(now=now + timedelta(seconds=5))
    assert app_job(client, obj["id"])["remote_record_id"] == first_id
    with SessionLocal() as db:
        assert db.scalar(select(func.count(MockSheetRecord.application_id))) == 1


@pytest.mark.parametrize("missing", ["remote", "link"])
def test_missing_remote_or_mapping_is_not_blindly_recreated(client, missing):
    obj = create(client).json()["data"]
    drain()
    with SessionLocal() as db:
        if missing == "remote":
            record = db.get(MockSheetRecord, obj["id"])
        else:
            record = db.scalar(select(RemoteLink))
        db.delete(record)
        db.commit()
    client.patch(
        f"/api/v1/applications/{obj['id']}",
        headers=headers(version=1),
        json={"stage": "screening", "change_reason": "虚构删除异常"},
    )
    drain()
    row = app_job(client, obj["id"])
    assert row["status"] == "dead"
    assert row["last_error"] == ("REMOTE_RECORD_MISSING" if missing == "remote" else "REMOTE_MAPPING_MISSING")
    assert client.get(f"/api/v1/applications/{obj['id']}").json()["data"]["stage"] == "screening"


def test_worker_lease_expiry_and_fenced_ack(client):
    obj = create(client).json()["data"]
    now = utcnow()
    first_token = sync.acquire(now)
    assert first_token and sync.acquire(now) is None
    first = None
    for _ in range(3):
        claim, found = sync.claim_next(first_token, now)
        if claim:
            first = claim
            break
        assert found
    assert first is not None
    later = now + timedelta(seconds=sync.LEASE_SECONDS + 1)
    second_token = sync.acquire(later)
    assert second_token and second_token != first_token
    assert sync.claim_next(first_token, later) == (None, False)
    second, _ = sync.claim_next(second_token, later)
    assert second and second.token != first.token
    sync.acknowledge(first, "MOCK-stale", None, later)
    assert app_job(client, obj["id"])["status"] == "processing"
    result = asyncio.run(MockSmartSheetAdapter().upsert_application(second.projection, second.remote_id))
    sync.acknowledge(second, result, None, later)
    assert app_job(client, obj["id"])["remote_record_id"] == result


def test_single_instance_lock_while_remote_io_and_no_db_checkout(client, monkeypatch):
    obj = create(client).json()["data"]
    checked_out = [0]
    counts_at_io = []

    def checkout(*_):
        checked_out[0] += 1

    def checkin(*_):
        checked_out[0] -= 1

    class Probe(MockSmartSheetAdapter):
        async def upsert_application(self, application, remote_record_id):
            counts_at_io.append(checked_out[0])
            assert await sync.process_batch() == 0
            return await super().upsert_application(application, remote_record_id)

    monkeypatch.setattr(sync, "sheet_adapter", lambda _: Probe())
    event.listen(engine, "checkout", checkout)
    event.listen(engine, "checkin", checkin)
    try:
        drain()
    finally:
        event.remove(engine, "checkout", checkout)
        event.remove(engine, "checkin", checkin)
    assert counts_at_io == [0]
    assert app_job(client, obj["id"])["status"] == "mock_synced"


def test_stale_snapshot_never_overwrites_newer_remote_and_soft_delete(client):
    obj = create(client).json()["data"]
    client.patch(
        f"/api/v1/applications/{obj['id']}",
        headers=headers(version=1),
        json={"stage": "screening", "change_reason": "虚构新版本"},
    )
    with SessionLocal() as db:
        old = db.scalar(select(Outbox).where(Outbox.entity_type == "applications", Outbox.version == 1))
        assert old is not None
        old.status, old.next_retry_at = "failed", utcnow() + timedelta(days=1)
        old.last_error = "REMOTE_TIMEOUT"
        db.commit()
    drain()
    with SessionLocal() as db:
        old = db.scalar(select(Outbox).where(Outbox.entity_type == "applications", Outbox.version == 1))
        assert old is not None
        old.next_retry_at = utcnow() - timedelta(seconds=1)
        db.commit()
    drain()
    with SessionLocal() as db:
        assert (
            db.scalar(select(Outbox.status).where(Outbox.entity_type == "applications", Outbox.version == 1))
            == "superseded"
        )
        assert (
            db.scalar(
                select(Outbox.last_error).where(Outbox.entity_type == "applications", Outbox.version == 1)
            )
            is None
        )
    response = client.request(
        "DELETE",
        f"/api/v1/applications/{obj['id']}",
        headers=headers(version=2),
        json={"change_reason": "虚构软删除"},
    )
    assert response.status_code == 200
    drain()
    records = asyncio.run(MockSmartSheetAdapter().list_remote_records())
    assert len(records) == 1 and records[0].deleted and records[0].version == 3


@pytest.mark.parametrize("configured", [False, True])
def test_tencent_config_never_silently_falls_back_or_claims_real_success(client, monkeypatch, configured):
    monkeypatch.setenv("SMARTSHEET_PROVIDER", "tencent_docs")
    if configured:
        monkeypatch.setenv("TENCENT_DOCS_TOKEN", "synthetic-not-a-real-token")
    obj = create(client).json()["data"]
    drain()
    row = app_job(client, obj["id"])
    assert row["provider"] == "tencent_docs" and row["mode"] == "real"
    assert row["status"] == "dead"
    assert row["last_error"] == ("BLOCKED_BY_SCHEMA" if configured else "BLOCKED_BY_CREDENTIALS")
    with SessionLocal() as db:
        assert db.scalar(select(func.count(MockSheetRecord.application_id))) == 0
    assert "synthetic-not-a-real-token" not in client.get("/api/v1/integrations/status").text


def test_provider_is_pinned_and_internal_events_not_sent(client, monkeypatch):
    obj = create(client).json()["data"]
    monkeypatch.setenv("SMARTSHEET_PROVIDER", "tencent_docs")
    drain()
    assert app_job(client, obj["id"])["provider"] == "mock"
    assert app_job(client, obj["id"])["status"] == "mock_synced"
    rows = client.get("/api/v1/sync/jobs").json()["data"]
    assert sum(row["internal_only"] for row in rows) == 2


def test_unknown_provider_error_does_not_persist_secrets(client, monkeypatch):
    obj = create(client).json()["data"]

    class Unsafe(MockSmartSheetAdapter):
        async def upsert_application(self, *_):
            raise SheetError("synthetic-secret-in-upstream", retryable=False)

    monkeypatch.setattr(sync, "sheet_adapter", lambda _: Unsafe())
    drain()
    assert app_job(client, obj["id"])["last_error"] == "INTERNAL_SYNC_ERROR"
    with SessionLocal() as db:
        assert "synthetic-secret-in-upstream" not in str(
            [row.metadata_json for row in db.scalars(select(AuditLog))]
        )


def test_legacy_error_is_not_exposed_or_copied_to_retry_audit(client):
    obj = create(client).json()["data"]
    with SessionLocal() as db:
        job = db.scalar(select(Outbox).where(Outbox.entity_type == "applications"))
        assert job is not None
        job.status, job.last_error = "dead", "synthetic-private-legacy-response"
        db.commit()
    row = app_job(client, obj["id"])
    assert row["last_error"] == "LEGACY_SYNC_ERROR"
    result = client.post(
        f"/api/v1/sync/jobs/{row['id']}/retry",
        headers=headers(version=row["revision"]),
        json={"reason": "核对历史失败"},
    )
    assert result.status_code == 200 and "private-legacy" not in result.text
    with SessionLocal() as db:
        assert "private-legacy" not in str([log.metadata_json for log in db.scalars(select(AuditLog))])


def test_summary_filter_and_routes_are_admin_only(client):
    create(client)
    for path in ("/api/v1/sync/jobs", "/api/v1/sync/summary", "/api/v1/integrations/status"):
        assert client.get(path, headers=headers("hr-a")).status_code == 403
    assert client.post("/api/v1/sync/run", headers=headers("manager-a")).status_code == 403
    assert client.get("/api/v1/sync/jobs?status=bogus").status_code == 422
    assert len(client.get("/api/v1/sync/jobs?status=pending").json()["data"]) == 3
    drain()
    assert client.get("/api/v1/sync/jobs?status=pending").json()["data"] == []


def test_lifespan_background_worker_runs_without_request_processing(client, monkeypatch):
    obj = create(client).json()["data"]
    monkeypatch.setenv("SYNC_WORKER_ENABLED", "true")
    with TestClient(app) as running:
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if app_job(running, obj["id"])["status"] == "mock_synced":
                break
            time.sleep(0.02)
        else:
            pytest.fail("Background worker did not process the committed outbox")
    with SessionLocal() as db:
        lease = db.get(SyncWorkerLease, "smartsheet")
        assert lease and lease.token is None


def test_payload_validation_failure_and_expired_claim_budget(client):
    obj = create(client).json()["data"]
    with SessionLocal() as db:
        job = db.scalar(select(Outbox).where(Outbox.entity_type == "applications"))
        assert job is not None
        job.payload_json = {"schema_version": 999}
        db.commit()
    drain()
    assert app_job(client, obj["id"])["last_error"] == "INVALID_PROJECTION"
    with SessionLocal() as db:
        job = db.scalar(select(Outbox).where(Outbox.entity_type == "applications"))
        assert job is not None
        job.status, job.cycle_attempts = "processing", sync.MAX_ATTEMPTS
        job.next_retry_at = utcnow() - timedelta(seconds=1)
        job.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    drain()
    assert app_job(client, obj["id"])["last_error"] == "CLAIM_EXPIRED"
    assert app_job(client, obj["id"])["next_retry_at"] is None
