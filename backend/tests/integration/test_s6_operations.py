import json
from pathlib import Path

import pytest
from sqlalchemy import event, func, select

from app.core.errors import BusinessError
from app.core.runtime import validate_runtime
from app.core.security import SYNC_ACTOR_ID
from app.db import AuditLog, AuthIdentity, Outbox, SessionLocal, User, WorkerState, engine, utcnow
from app.services.common import mutate
from scripts.admin.users import provision, revoke
from scripts.operations.backup import backup, checksum, restore
from tests.helpers import create


def test_sqlite_backup_restore_preserves_facts_and_never_overwrites(client, tmp_path):
    create(client)
    with SessionLocal() as db:
        db.add(WorkerState(name="background-runtime", owner_token="synthetic-owner", expires_at=utcnow()))
        db.commit()
    assert engine.url.database is not None
    source = Path(engine.url.database)
    destination, restored = tmp_path / "backup.db", tmp_path / "restored.db"
    before = checksum(source)
    report = backup(source, destination)
    assert report["counts"]["applications"] == 1 and report["sha256"] == checksum(destination)
    assert checksum(source) == before
    result = restore(destination, restored)
    assert result["counts"] == report["counts"] and result["schema_revision"] == "0006_s6"
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(restored)) as db:
        assert db.execute("SELECT owner_token FROM worker_states").fetchone()[0] is None
        assert db.execute("SELECT application_code FROM applications").fetchone()[0] == "A10001"
    for target in (source, restored):
        with pytest.raises(ValueError, match="DESTINATION_MUST_BE_NEW"):
            restore(destination, target)
    assert checksum(source) == before


def test_backup_manifest_corruption_rejected_before_target_creation(client, tmp_path):
    assert engine.url.database is not None
    path = tmp_path / "backup.db"
    backup(Path(engine.url.database), path)
    manifest = Path(str(path) + ".manifest.json")
    data = json.loads(manifest.read_text())
    data["sha256"] = "0" * 64
    manifest.write_text(json.dumps(data))
    target = tmp_path / "restored.db"
    with pytest.raises(ValueError, match="BACKUP_CHECKSUM_FAILED"):
        restore(path, target)
    assert not target.exists()


def test_operator_provision_replay_no_implicit_role_change_and_revoke(client):
    args = dict(issuer="https://identity.example.test", subject="synthetic-employee", name="虚构授权HR", role="HR", department="engineering")
    with SessionLocal() as db:
        actor = db.get(User, SYNC_ACTOR_ID)
        assert actor is not None
        first = mutate(db, actor, "provision", "synthetic-provision-key", args, lambda: provision(db, actor, **args))
        same = mutate(db, actor, "provision", "synthetic-provision-key", args, lambda: provision(db, actor, **args))
        assert first == same
        assert db.scalar(select(func.count(AuthIdentity.id))) == 1
        assert db.scalar(select(func.count(AuditLog.id))) == 2
        assert db.scalar(select(func.count(Outbox.id))) == 2
        with pytest.raises(BusinessError):
            provision(db, actor, **{**args, "role": "ADMIN"})
        db.rollback()
        revoked = mutate(db, actor, "revoke", "synthetic-revoke", {"version": first["version"]},
            lambda: revoke(db, actor, first["identity_id"], first["version"], "虚构授权撤销"))
        assert revoked["active"] is False and revoked["version"] == 2


def test_ai_settings_audit_failure_rolls_back_key_and_config(client):
    def broken(*_):
        raise RuntimeError("synthetic audit failure")
    event.listen(Outbox, "before_insert", broken)
    try:
        with pytest.raises(RuntimeError, match="synthetic audit failure"):
            client.patch("/api/v1/settings/ai", headers={"If-Match": "1", "Idempotency-Key": "synthetic-rollback"},
                json={"provider": "mock", "model": "synthetic-model", "api_key": "synthetic-secret", "change_reason": "虚构验证"})
    finally:
        event.remove(Outbox, "before_insert", broken)
    response = client.get("/api/v1/settings/ai").json()["data"]
    assert response["version"] == 1 and not response["has_api_key"]


@pytest.mark.parametrize("field,value", [
    ("AUTH_MODE", "dev"), ("DEV_AUTH_ENABLED", "true"), ("RATE_LIMIT_ENABLED", "false"),
    ("SSO_AUDIENCE", ""), ("SESSION_CSRF_SECRET", "short"), ("SSO_PUBLIC_KEY_FILE", "missing-file"),
    ("APP_SECRET_KEY", "bad-key"), ("ALLOWED_ORIGINS", "*"), ("WECOM_SEND_ENABLED", "true"),
    ("MOCK_SHEET_FAILURE", "timeout"), ("DEV_PROXY_NETWORKS", "172.30.123.0/24"),
])
def test_production_configuration_fail_closed(client, monkeypatch, tmp_path, field, value):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / "public.pem"
    path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    for name, default in {"APP_ENV": "production", "AUTH_MODE": "sso", "DEV_AUTH_ENABLED": "false", "APP_PUBLIC_URL": "https://recruit.example.test",
        "ALLOWED_ORIGINS": "https://recruit.example.test", "SSO_ISSUER": "https://identity.example.test", "SSO_AUDIENCE": "synthetic",
        "SESSION_CSRF_SECRET": "synthetic-at-least-32-bytes-csrf-secret", "SSO_PUBLIC_KEY_FILE": str(path)}.items():
        monkeypatch.setenv(name, default)
    monkeypatch.setenv(field, value)
    with pytest.raises(RuntimeError):
        validate_runtime()
