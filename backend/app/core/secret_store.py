"""Encrypted managed secrets; master key is exclusively server-side."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import BACKEND_ROOT

AAD = b"recruitflow:deepseek-api-key:v1"


def master_key():
    value = os.getenv("APP_SECRET_KEY")
    if not value and os.getenv("APP_ENV", "development") == "development":
        path = BACKEND_ROOT / ".secrets" / "ai-master.key"
        path.parent.mkdir(mode=0o700, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(base64.urlsafe_b64encode(os.urandom(32)).decode())
        except FileExistsError:
            pass
        value = path.read_text(encoding="utf-8").strip()
    try:
        key = base64.b64decode(value or "", altchars=b"-_", validate=True)
        if len(key) != 32:
            raise ValueError()
        return key
    except (ValueError, TypeError):
        raise RuntimeError("Server secret-store master key is missing or invalid") from None


def ready():
    try:
        master_key()
        return True
    except (RuntimeError, OSError):
        return False


def encrypt(value):
    nonce = os.urandom(12)
    return base64.urlsafe_b64encode(nonce + AESGCM(master_key()).encrypt(nonce, value.encode(), AAD)).decode()


def decrypt(value):
    data = base64.urlsafe_b64decode(value)
    return AESGCM(master_key()).decrypt(data[:12], data[12:], AAD).decode()
