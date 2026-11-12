"""Validate gateway-issued sessions; database mappings alone determine authorization."""

import hashlib
import hmac
import os
import time

import jwt
from sqlalchemy import select

from app.core.errors import BusinessError
from app.core.runtime import public_origin, sso_public_key
from app.db import AuthIdentity, User

COOKIE_NAME = "__Host-recruitflow_session"


def csrf_for(token):
    return hmac.new(os.environ["SESSION_CSRF_SECRET"].encode(), token.encode(), hashlib.sha256).hexdigest()


def session_user(request, db, token):
    if request.headers.get("X-Dev-User") is not None or request.headers.get("X-User-Role") is not None:
        raise BusinessError(403, "DEV_IDENTITY_FORBIDDEN", "当前认证模式不接受开发身份头")
    if not token or len(token) > 8192:
        raise BusinessError(401, "UNAUTHENTICATED", "请通过企业登录入口访问系统")
    try:
        claims = jwt.decode(token, sso_public_key(), algorithms=["RS256"],
            issuer=os.environ["SSO_ISSUER"], audience=os.environ["SSO_AUDIENCE"],
            options={"require": ["exp", "iat", "sub", "iss", "aud", "jti"], "strict_aud": True})
        if (type(claims["iat"]) is not int or type(claims["exp"]) is not int
                or not 0 < claims["exp"] - claims["iat"] <= 3600
                or claims["iat"] > time.time()
                or not isinstance(claims["sub"], str) or not 1 <= len(claims["sub"]) <= 150
                or not isinstance(claims["jti"], str) or not 1 <= len(claims["jti"]) <= 150):
            raise ValueError()
    except (jwt.PyJWTError, ValueError, RuntimeError, KeyError):
        raise BusinessError(401, "UNAUTHENTICATED", "企业会话无效或已过期，请重新登录") from None
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        expected = csrf_for(token)
        if request.headers.get("Origin") != public_origin() or not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), expected):
            raise BusinessError(403, "CSRF_REJECTED", "请求来源或会话校验失败，请刷新登录后重试")
    user = db.scalar(select(User).join(AuthIdentity, AuthIdentity.user_id == User.id).where(
        AuthIdentity.issuer == claims["iss"], AuthIdentity.subject == claims["sub"], AuthIdentity.active.is_(True),
        AuthIdentity.deleted_at.is_(None), User.active.is_(True), User.deleted_at.is_(None)))
    if user is None:
        raise BusinessError(403, "IDENTITY_NOT_PROVISIONED", "企业身份未授权或已停用，请联系管理员")
    request.state.csrf_token = csrf_for(token)
    return user
