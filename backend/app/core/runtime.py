"""Fail-closed server configuration; never include values in diagnostics."""

import base64
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key


def production():
    return os.getenv("APP_ENV", "development") == "production"


def auth_mode():
    return os.getenv("AUTH_MODE", "dev")


def flag(name, default="false"):
    value = os.getenv(name, default).lower()
    if value not in {"true", "false"}:
        raise RuntimeError(f"Invalid boolean configuration: {name}")
    return value == "true"


def public_origin():
    value = os.getenv("APP_PUBLIC_URL", "")
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
        raise RuntimeError("APP_PUBLIC_URL must be an explicit HTTPS origin")
    return value.rstrip("/")


def gateway_path(name):
    path = os.getenv(name, "")
    if path and (not path.startswith("/") or path.startswith("//") or "\\" in path or any(c in path for c in ("\r", "\n", "?", "#"))):
        raise RuntimeError(f"Invalid same-origin gateway path: {name}")
    return path or None


def sso_public_key():
    try:
        path = Path(os.environ["SSO_PUBLIC_KEY_FILE"])
        if path.stat().st_size > 16384:
            raise ValueError()
        key = load_pem_public_key(path.read_bytes())
        if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
            raise ValueError()
        return key
    except (OSError, ValueError, KeyError):
        raise RuntimeError("SSO_PUBLIC_KEY_FILE must contain an RSA public key of at least 2048 bits") from None


def validate_runtime():
    env, mode = os.getenv("APP_ENV", "development"), os.getenv("APP_MODE", "mock")
    if env not in {"development", "production"} or mode not in {"mock", "hybrid", "live"}:
        raise RuntimeError("Unsupported APP_ENV/APP_MODE")
    if auth_mode() not in {"dev", "sso"}:
        raise RuntimeError("AUTH_MODE must be dev or sso")
    if production() and (auth_mode() != "sso" or flag("DEV_AUTH_ENABLED", "true")):
        raise RuntimeError("Production requires AUTH_MODE=sso and DEV_AUTH_ENABLED=false")
    if auth_mode() == "sso":
        public_origin()
        issuer = urlsplit(os.getenv("SSO_ISSUER", ""))
        if issuer.scheme != "https" or not issuer.hostname or issuer.username or issuer.password or issuer.query or issuer.fragment:
            raise RuntimeError("SSO_ISSUER must be an explicit HTTPS issuer")
        if not os.getenv("SSO_AUDIENCE") or len(os.getenv("SESSION_CSRF_SECRET", "")) < 32:
            raise RuntimeError("SSO_AUDIENCE and strong SESSION_CSRF_SECRET are required")
        sso_public_key()
        gateway_path("SSO_LOGIN_PATH")
        gateway_path("SSO_LOGOUT_PATH")
    if production():
        from app.core.secret_store import master_key

        master_key()
        if not flag("RATE_LIMIT_ENABLED", "true") or os.getenv("MOCK_SHEET_FAILURE", "none") != "none":
            raise RuntimeError("Production requires rate limiting and forbids fault injection")
        if os.getenv("DEV_PROXY_NETWORKS"):
            raise RuntimeError("Production forbids development proxy networks")
        origins = os.getenv("ALLOWED_ORIGINS", public_origin()).split(",")
        if origins != [public_origin()]:
            raise RuntimeError("Production CORS must match APP_PUBLIC_URL exactly")
    for field, default in (("REQUEST_RATE_PER_MINUTE", "600"), ("INGESTION_RATE_PER_MINUTE", "30")):
        try:
            if not 1 <= int(os.getenv(field, default)) <= 100000:
                raise ValueError()
        except ValueError:
            raise RuntimeError(f"Invalid rate limit: {field}") from None
    for raw in filter(None, os.getenv("DEV_PROXY_NETWORKS", "").split(",")):
        network = ipaddress.ip_network(raw)
        if not network.is_private or network.prefixlen < 24:
            raise RuntimeError("Development proxy network must be private and narrowly scoped")
    ai, sheet, wecom = os.getenv("AI_PROVIDER", "mock"), os.getenv("SMARTSHEET_PROVIDER", "mock"), os.getenv("WECOM_PROVIDER", "mock")
    if ai not in {"mock", "deepseek"} or sheet not in {"mock", "tencent_docs"} or wecom not in {"mock", "wecom"}:
        raise RuntimeError("Invalid connector provider")
    if mode == "mock" and (ai, sheet, wecom) != ("mock", "mock", "mock"):
        raise RuntimeError("Mock mode cannot enable real connectors")
    if production() or mode == "live":
        if ai == "deepseek" and (not os.getenv("DEEPSEEK_API_KEY") or not os.getenv("DEEPSEEK_MODEL")):
            raise RuntimeError("DeepSeek credentials/model required")
        if sheet == "tencent_docs":
            raise RuntimeError("Tencent writes blocked: authorized tool schemas/mapping remain unverified")
        for enabled, keys in (("WECOM_CALLBACK_ENABLED", ("WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_CALLBACK_TOKEN", "WECOM_ENCODING_AES_KEY")),
                              ("WECOM_SEND_ENABLED", ("WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_SECRET"))):
            if flag(enabled):
                if wecom != "wecom" or not all(os.getenv(k) for k in keys):
                    raise RuntimeError(f"Missing explicit WeCom configuration: {enabled}")
                try:
                    if int(os.environ["WECOM_AGENT_ID"]) <= 0:
                        raise ValueError()
                    if enabled == "WECOM_CALLBACK_ENABLED" and len(base64.b64decode(os.environ["WECOM_ENCODING_AES_KEY"] + "=", validate=True)) != 32:
                        raise ValueError()
                except ValueError:
                    raise RuntimeError("Invalid WeCom agent/AES configuration") from None
    if mode == "live":
        raise RuntimeError("Live mode requires verified Tencent schemas and authorized integrations; unavailable until real acceptance")
