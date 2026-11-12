"""Isolated production-mode Mock HTTP check with a synthetic SSO signer; no real IdP/TLS."""

import base64
import os
import secrets
import socket
import subprocess
import sys
import time
import uuid

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import BACKEND_ROOT, PROJECT_ROOT


def main():
    root = (PROJECT_ROOT / ".tools" / ("s6-security-" + uuid.uuid4().hex[:8])).resolve()
    assert root.is_relative_to(PROJECT_ROOT.resolve())
    root.mkdir(parents=True)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = root / "public.pem"
    public.write_bytes(private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    app_key, csrf_key = base64.urlsafe_b64encode(os.urandom(32)).decode(), secrets.token_urlsafe(48)
    for name, value in (("app.key", app_key), ("csrf.key", csrf_key)):
        (root / name).write_text(value)
    origin, issuer = "https://recruit.example.test", "https://identity.example.test"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DEEPSEEK_", "WECOM_", "TENCENT_", "SSO_", "SESSION_", "APP_SECRET_"))}
    env.update(APP_ENV="production", APP_MODE="mock", AUTH_MODE="sso", DEV_AUTH_ENABLED="false", DEV_PROXY_NETWORKS="",
        APP_PUBLIC_URL=origin, ALLOWED_ORIGINS=origin, SSO_ISSUER=issuer, SSO_AUDIENCE="synthetic-recruitflow",
        SSO_PUBLIC_KEY_FILE=str(public), APP_SECRET_KEY_FILE=str(root / "app.key"),
        SESSION_CSRF_SECRET_FILE=str(root / "csrf.key"), DATABASE_URL="sqlite:///" + (root / "test.db").as_posix(),
        AI_PROVIDER="mock", SMARTSHEET_PROVIDER="mock", WECOM_PROVIDER="mock", MOCK_SHEET_FAILURE="none", RATE_LIMIT_ENABLED="true",
        SYNC_WORKER_ENABLED="true", WECOM_WORKER_ENABLED="true")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_ROOT, env=env, check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "scripts.admin.users", "provision", "--issuer", issuer,
        "--subject", "synthetic-admin", "--name", "虚构安全验收管理员", "--department", "synthetic", "--role", "ADMIN"],
        cwd=BACKEND_ROOT, env=env, check=True, capture_output=True)
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    log_path = root / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log", "--no-proxy-headers"],
            cwd=BACKEND_ROOT, env=env, stdout=log, stderr=log)
        try:
            now = int(time.time())
            token = jwt.encode({"iss": issuer, "aud": "synthetic-recruitflow", "sub": "synthetic-admin",
                "iat": now, "exp": now + 600, "jti": uuid.uuid4().hex, "role": "MANAGER"}, private, algorithm="RS256")
            with httpx.Client(base_url=f"http://127.0.0.1:{port}/api/v1", headers={"Host": "recruit.example.test"}, trust_env=False, timeout=3) as client:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise AssertionError("Isolated server stopped before readiness")
                    try:
                        if client.get("/readyz").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    raise AssertionError("Isolated production-mode server not ready")
                assert client.get("/me").status_code == 401
                assert client.get("/health", headers={"X-Dev-User": "admin"}).status_code == 403
                client.headers["Cookie"] = "__Host-recruitflow_session=" + token
                me = client.get("/me").json()["data"]
                assert me["user"]["role"] == "ADMIN" and me["authentication"] == "sso_cookie"
                assert client.get("/dev/users").status_code == 403
                body = {"provider": "mock", "model": "synthetic-model", "api_key": "synthetic-managed-key", "change_reason": "虚构隔离验收"}
                assert client.patch("/settings/ai", json=body, headers={"If-Match": "1", "Idempotency-Key": uuid.uuid4().hex}).status_code == 403
                response = client.patch("/settings/ai", json=body, headers={"If-Match": "1", "Idempotency-Key": uuid.uuid4().hex,
                    "Origin": origin, "X-CSRF-Token": me["csrf_token"]})
                assert response.status_code == 200 and response.json()["data"]["has_api_key"]
                assert "synthetic-managed-key" not in response.text
                assert client.get("/ops/status").json()["data"]["lease_healthy"]
                assert client.get("http://127.0.0.1:" + str(port) + "/openapi.json").status_code == 404
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    logs = log_path.read_text(encoding="utf-8")
    assert not any(secret in logs for secret in (app_key, csrf_key, token, "synthetic-managed-key"))
    print("PASS: isolated production-mode Mock + signed SSO cookie + DB roles + CSRF + dev-header rejection + encrypted AI settings + worker health + safe logs")
    print("Synthetic artifacts retained in ignored .tools; no real SSO, external connector or Docker execution")


if __name__ == "__main__":
    main()
