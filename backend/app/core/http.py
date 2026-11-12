from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app import schemas as s
from app.core.errors import BusinessError
from app.core.runtime import flag, production, public_origin


def safe_error(request_id, status, code, message):
    return JSONResponse(status_code=status, content={"request_id": request_id,
        "error": {"code": code, "message": message, "details": {}}})


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            return await self.app(scope, receive, send)
        body = bytearray()
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > 65536:
                        response = safe_error(scope.get("state", {}).get("request_id", ""), 413, "BODY_TOO_LARGE", "请求体超过64KiB限制")
                        return await response(scope, receive, send)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await safe_error(scope.get("state", {}).get("request_id", ""), 408, "BODY_TIMEOUT", "请求体接收超时")(scope, receive, send)
        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, buffered_receive, send)


def configure_http(app: FastAPI):
    app.add_middleware(BodyLimitMiddleware)
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = "req_" + uuid.uuid4().hex
        started = time.monotonic()
        response = None
        host = urlsplit("http://" + request.headers.get("host", "")).hostname
        allowed = {urlsplit(public_origin()).hostname} if production() else {"localhost", "127.0.0.1", "::1", "testserver"}
        if host not in allowed:
            response = safe_error(request.state.request_id, 400, "INVALID_HOST", "请求主机不在允许范围")
        elif production() and request.url.path in {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}:
            response = safe_error(request.state.request_id, 404, "NOT_FOUND", "接口不存在")
        elif production() and ("x-dev-user" in request.headers or "x-user-role" in request.headers):
            response = safe_error(request.state.request_id, 403, "DEV_IDENTITY_FORBIDDEN", "生产不接受开发身份头")
        elif flag("RATE_LIMIT_ENABLED", "true") and request.url.path != "/api/v1/health":
            peer = request.client.host if request.client else "unknown"
            retry = request.app.state.rate_limiter.check("ip:" + peer, int(os.getenv("REQUEST_RATE_PER_MINUTE", "600")))
            if retry:
                response = safe_error(request.state.request_id, 429, "RATE_LIMITED", "请求过于频繁，请稍后重试")
                response.headers["Retry-After"] = str(retry)
        if response is None:
            try:
                response = await call_next(request)
            except Exception:
                logging.getLogger(__name__).error("request_failed", extra={"request_id": request.state.request_id,
                    "route": getattr(request.scope.get("route"), "path", "unmatched"), "method": request.method, "status": 500})
                raise
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if production():
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        route = getattr(request.scope.get("route"), "path", "unmatched")
        logging.getLogger(__name__).info("request_complete", extra={"request_id": request.state.request_id,
            "route": route, "method": request.method, "status": response.status_code,
            "duration_ms": round((time.monotonic() - started) * 1000, 2)})
        return response

    def error_response(request: Request, status: int, code: str, message: str, details: dict | None = None):
        body = s.ErrorResponse(
            error=s.ApiError(code=code, message=message, details=details or {}),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=status,
            content=body.model_dump(mode="json"),
            headers={"X-Request-ID": body.request_id, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.exception_handler(BusinessError)
    async def business_error(request: Request, exc: BusinessError):
        response = error_response(request, exc.status, exc.code, exc.message)
        if exc.status == 429:
            response.headers["Retry-After"] = str(getattr(request.state, "retry_after", 60))
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(request, exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [{"field": ".".join(map(str, item["loc"])), "type": item["type"]} for item in exc.errors()]
        return error_response(request, 422, "INVALID_INPUT", "请求字段不符合契约", {"fields": fields})

    @app.exception_handler(Exception)
    async def internal_error(request: Request, _exc: Exception):
        return error_response(request, 500, "INTERNAL_ERROR", "内部处理失败，请提供请求编号排查")
