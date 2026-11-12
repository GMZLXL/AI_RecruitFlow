import os
from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr

from app import schemas as s
from app.core import secret_store
from app.db import AISettings, SessionLocal
from app.integrations.parsers.privacy import redact

from .common import conditional_update, fail, record_change, snapshot

SETTINGS_ID = "e706db16-1bbd-415d-bbfd-5156558a6089"


@dataclass(frozen=True)
class AIConnection:
    provider: Literal["mock", "deepseek"]
    model: str
    api_key: SecretStr


def metadata(db):
    row = db.get(AISettings, SETTINGS_ID)
    provider = (row.provider if row and row.provider else os.getenv("AI_PROVIDER", "mock"))
    model = row.model if row and row.model else os.getenv("DEEPSEEK_MODEL", "")
    managed = bool(row and row.api_key_ciphertext)
    environment = not (row and row.key_override) and bool(os.getenv("DEEPSEEK_API_KEY"))
    has_key = managed or environment
    store_ready = secret_store.ready()
    allowed = os.getenv("APP_MODE", "mock") == "hybrid"
    status = "mock_only" if provider == "mock" else "mode_mismatch" if not allowed else "configured_not_verified" if has_key and (not managed or store_ready) else "blocked_by_credentials"
    return s.AISettingsRead(version=row.version if row else 1,
        provider="deepseek" if provider == "deepseek" else "mock", model=model, has_api_key=has_key,
        key_source="managed" if managed else "environment" if environment else "none",
        secret_store_ready=store_ready, real_calls_allowed=allowed, status=status)


def connection():
    with SessionLocal() as db:
        info = metadata(db)
        row = db.get(AISettings, SETTINGS_ID)
        key = os.getenv("DEEPSEEK_API_KEY", "") if not row or not row.key_override else ""
        if row and row.api_key_ciphertext:
            try:
                key = secret_store.decrypt(row.api_key_ciphertext)
            except Exception:
                key = ""  # never fall back to another secret after a managed-secret failure
        return AIConnection(info.provider, info.model, SecretStr(key))


def save(db, actor, data, expected):
    row = db.get(AISettings, SETTINGS_ID)
    if row is None:
        row = AISettings(id=SETTINGS_ID)
        db.add(row)
        db.flush()
    before = snapshot(row)
    values = {"provider": data.provider, "model": data.model}
    existing = metadata(db)
    has_key = existing.has_api_key
    if data.clear_api_key:
        values.update(api_key_ciphertext=None, key_override=True)
        has_key = False
    elif data.api_key is not None:
        try:
            values.update(api_key_ciphertext=secret_store.encrypt(data.api_key.get_secret_value()), key_override=True)
        except (RuntimeError, OSError):
            fail(503, "SECRET_STORE_NOT_READY", "服务端密钥存储未就绪，请联系管理员配置加密主密钥")
        has_key = True
    if data.provider == "deepseek":
        if not existing.real_calls_allowed:
            fail(409, "REAL_AI_NOT_ALLOWED", "当前环境禁止真实AI调用；可保存Key并保持Mock，启用需管理员允许真实调用")
        if not has_key:
            fail(400, "API_KEY_REQUIRED", "启用DeepSeek前需配置API Key")
    conditional_update(db, row, expected, values)
    reason = redact(data.change_reason)
    if data.api_key is not None:
        reason = reason.replace(data.api_key.get_secret_value(), "[credential]")
    record_change(db, row, actor, "configure_ai", before, reason)
    return metadata(db)
