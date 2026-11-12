import asyncio
import base64
import io
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app.core.logging import SafeJsonFormatter
from app.core.runtime import validate_runtime
from app.core.security import DEV_IDS
from app.core.sso import COOKIE_NAME
from app.db import AISettings, AuditLog, AuthIdentity, Outbox, SessionLocal, WorkerState, utcnow
from app.jobs import runtime
from app.services.ai_settings import SETTINGS_ID, connection
from tests.helpers import create, headers

BASE = "/api/v1"


@pytest.fixture
def sso(client, monkeypatch, tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = tmp_path / "synthetic-public.pem"
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    for name, value in {"APP_ENV": "production", "AUTH_MODE": "sso", "DEV_AUTH_ENABLED": "false",
        "APP_PUBLIC_URL": "https://recruit.example.test", "ALLOWED_ORIGINS": "https://recruit.example.test",
        "SSO_ISSUER": "https://id.example.test", "SSO_AUDIENCE": "synthetic-recruitflow",
        "SSO_PUBLIC_KEY_FILE": str(public), "SESSION_CSRF_SECRET": "synthetic-csrf-secret-at-least-32-bytes"}.items():
        monkeypatch.setenv(name, value)
    with SessionLocal() as db:
        db.add(AuthIdentity(issuer="https://id.example.test", subject="synthetic-hr", user_id=DEV_IDS["hr-a"]))
        db.commit()

    def token(**overrides):
        claims = {"iss": "https://id.example.test", "aud": "synthetic-recruitflow", "sub": "synthetic-hr",
            "iat": int(time.time()), "exp": int(time.time()) + 600, "jti": uuid.uuid4().hex, "role": "ADMIN"}
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm="RS256")

    client.base_url = "https://recruit.example.test"
    client.cookies.set(COOKIE_NAME, token())
    return token


def test_sso_claims_do_not_grant_roles_csrf_and_no_dev_directory(client, sso):
    validate_runtime()
    identity = client.get(BASE + "/me")
    assert identity.status_code == 200, identity.text
    data = identity.json()["data"]
    assert data["authentication"] == "sso_cookie" and data["user"]["role"] == "HR"
    assert data["csrf_token"] and data["user"]["id"] == DEV_IDS["hr-a"]
    assert client.get(BASE + "/dev/users").status_code == 403
    assert client.get(BASE + "/ops/status").status_code == 403
    assert client.get(BASE + "/me", headers={"X-Dev-User": "admin"}).status_code == 403
    body = {"display_name": "虚构企业候选人"}
    denied = client.post(BASE + "/candidates", json=body, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "CSRF_REJECTED"
    h = {"Idempotency-Key": uuid.uuid4().hex, "X-CSRF-Token": data["csrf_token"], "Origin": "https://recruit.example.test"}
    assert client.post(BASE + "/candidates", json=body, headers=h).status_code == 201
    assert client.post(BASE + "/candidates", json=body, headers={**h, "Origin": "https://evil.example"}).status_code == 403
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


@pytest.mark.parametrize("changes", [
    {"iss": "https://evil.example"}, {"aud": "wrong"}, {"exp": 1}, {"iat": int(time.time()) + 9999},
    {"sub": "unknown"}, {"jti": ""}, {"exp": int(time.time()) + 7200}, {"aud": ["synthetic-recruitflow"]},
])
def test_invalid_sso_sessions_refused(client, sso, changes):
    client.cookies.set(COOKIE_NAME, sso(**changes))
    assert client.get(BASE + "/me").status_code in {401, 403}


def test_sso_signature_and_revocation(client, sso):
    client.cookies.set(COOKIE_NAME, jwt.encode({"sub": "synthetic-hr"}, "synthetic-long-untrusted-secret-extra", algorithm="HS256"))
    assert client.get(BASE + "/me").status_code == 401
    client.cookies.set(COOKIE_NAME, sso())
    with SessionLocal() as db:
        row = db.scalar(select(AuthIdentity))
        assert row is not None
        row.active = False
        db.commit()
    assert client.get(BASE + "/me").status_code == 403


def test_host_limit_body_and_security_headers(client, monkeypatch):
    monkeypatch.setenv("REQUEST_RATE_PER_MINUTE", "2")
    assert client.get(BASE + "/auth/config").status_code == 200
    assert client.get(BASE + "/auth/config").status_code == 200
    limited = client.get(BASE + "/auth/config")
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    assert limited.headers["Cache-Control"] == "no-store"
    assert limited.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get(BASE + "/health").status_code == 200
    assert client.get(BASE + "/health", headers={"Host": "evil.example"}).status_code == 400
    monkeypatch.setenv("REQUEST_RATE_PER_MINUTE", "600")
    response = client.post(BASE + "/ingestions", content=b"x" * 65537)
    assert response.status_code == 413


def test_actor_ingestion_limit_is_not_browser_identity_role(client, monkeypatch):
    monkeypatch.setenv("INGESTION_RATE_PER_MINUTE", "1")
    assert client.post(BASE + "/ingestions", json={"text": "虚构待审核消息"}).status_code == 200
    assert client.post(BASE + "/ingestions", json={"text": "虚构另一条"}).status_code == 429
    assert client.post(BASE + "/ingestions", headers={"X-Dev-User": "hr-a"}, json={"text": "虚构本人消息"}).status_code == 200


def test_safe_logging_omits_key_query_body_and_exception():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(SafeJsonFormatter())
    logger = logging.getLogger("synthetic.s6")
    logger.handlers, logger.propagate = [handler], False
    logger.setLevel(logging.INFO)
    logger.error("https://qyapi.weixin.qq.com?access_token=synthetic-private-key candidate 13800138000")
    try:
        raise RuntimeError("synthetic-private-key")
    except RuntimeError:
        logger.exception("worker_cycle_failed")
    value = output.getvalue()
    assert "synthetic-private-key" not in value and "13800138000" not in value and "access_token" not in value
    assert json.loads(value.splitlines()[1])["event"] == "worker_cycle_failed"


def test_worker_single_leader_fence_and_expired_recovery(client):
    tokens = [str(uuid.uuid4()), str(uuid.uuid4())]
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(runtime.acquire, tokens))
    assert sum(result) == 1
    leader, other = (tokens[0], tokens[1]) if result[0] else (tokens[1], tokens[0])
    assert runtime.renew(leader) and not runtime.renew(other)
    with SessionLocal() as db:
        row = db.get(WorkerState, runtime.NAME)
        assert row is not None
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert runtime.acquire(other)
    runtime.release(leader)
    assert runtime.renew(other)
    runtime.release(other)


def test_supervisor_standby_does_not_start_duplicate_tasks(client):
    async def run():
        seen = []
        async def runner():
            seen.append("started")
            await asyncio.Event().wait()
        first, second = SimpleNamespace(state=SimpleNamespace()), SimpleNamespace(state=SimpleNamespace())
        one = asyncio.create_task(runtime.supervise(first, [runner], interval=0.01))
        two = asyncio.create_task(runtime.supervise(second, [runner], interval=0.01))
        for _ in range(50):
            if seen:
                break
            await asyncio.sleep(0.01)
        assert len(seen) == 1
        assert {first.state.worker_role, second.state.worker_role} == {"leader", "standby"}
        one.cancel()
        two.cancel()
        await asyncio.gather(one, two, return_exceptions=True)
    asyncio.run(run())


def test_ops_status_is_real_and_admin_only(client):
    create(client)
    runtime.record_cycle("sync", True)
    runtime.record_cycle("wecom", False)
    data = client.get(BASE + "/ops/status").json()["data"]
    assert data["schema_revision"] == "0006_s6" and data["database"] == "ok"
    assert sum(data["sync_counts"].values()) == 1
    assert data["workers"][1]["last_error"] == "WORKER_CYCLE_FAILED"
    assert client.get(BASE + "/ops/status", headers=headers("hr-a")).status_code == 403
    assert client.get(BASE + "/readyz").status_code == 200


def ai_request(client, key="synthetic-api-key-please-never-return", **changes):
    read = client.get(BASE + "/settings/ai").json()["data"]
    body = {"provider": "mock", "model": "synthetic-model", "api_key": key, "change_reason": "虚构配置验证", **changes}
    h = headers(version=read["version"])
    return client.patch(BASE + "/settings/ai", json=body, headers=h), body, h


def test_ai_key_encrypted_atomic_no_echo_and_key_hash_idempotency(client):
    secret = "synthetic-api-key-please-never-return"
    response, body, h = ai_request(client, secret, change_reason="虚构测试 " + secret)
    assert response.status_code == 200, response.text
    assert secret not in response.text and response.json()["data"]["has_api_key"]
    assert client.patch(BASE + "/settings/ai", headers=h, json=body).json()["data"]["version"] == 2
    assert client.patch(BASE + "/settings/ai", headers=h, json={**body, "api_key": "different-synthetic-key"}).status_code == 409
    with SessionLocal() as db:
        settings = db.get(AISettings, SETTINGS_ID)
        assert settings is not None and settings.api_key_ciphertext and secret not in settings.api_key_ciphertext
        for model in (AuditLog, Outbox):
            rows = db.scalars(select(model)).all()
            assert secret not in str([getattr(row, "metadata_json", getattr(row, "payload_json", {})) for row in rows])
    assert connection().api_key.get_secret_value() == secret
    assert client.get(BASE + "/settings/ai", headers=headers("hr-a")).status_code == 403
    assert client.patch(BASE + "/settings/ai", headers=headers("hr-a", 2), json=body).status_code == 403


def test_ai_mode_guard_preserve_clear_and_effective_factory(client, monkeypatch):
    assert ai_request(client, provider="deepseek")[0].status_code == 409
    monkeypatch.setenv("APP_MODE", "hybrid")
    response, _, _ = ai_request(client, provider="deepseek")
    assert response.status_code == 200
    from app.integrations.parsers.deepseek import DeepSeekParser
    from app.integrations.parsers.factory import get_parser
    parser = get_parser()
    assert isinstance(parser, DeepSeekParser)
    assert parser.connection is not None and parser.connection.model == "synthetic-model"
    read = response.json()["data"]
    body = {"provider": "mock", "model": "synthetic-model-2", "change_reason": "保留Key"}
    kept = client.patch(BASE + "/settings/ai", json=body, headers=headers(version=read["version"]))
    assert kept.json()["data"]["has_api_key"]
    cleared = client.patch(BASE + "/settings/ai", json={**body, "clear_api_key": True}, headers=headers(version=kept.json()["data"]["version"]))
    assert cleared.status_code == 200 and not cleared.json()["data"]["has_api_key"]
    assert not connection().api_key.get_secret_value()


def test_ai_secret_store_missing_or_changed_does_not_fall_back(client, monkeypatch):
    response, _, _ = ai_request(client)
    assert response.status_code == 200
    monkeypatch.setenv("APP_SECRET_KEY", base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-other-environment-key")
    assert connection().api_key.get_secret_value() == ""
    monkeypatch.setenv("APP_SECRET_KEY", "bad-key")
    read = client.get(BASE + "/settings/ai").json()["data"]
    assert not read["secret_store_ready"]
    response = client.patch(BASE + "/settings/ai", headers=headers(version=read["version"]),
        json={"provider": "mock", "model": "synthetic-model", "api_key": "synthetic-new", "change_reason": "测试错误密钥"})
    assert response.status_code == 503 and "synthetic-new" not in response.text
