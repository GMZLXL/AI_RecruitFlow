from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app import schemas as s
from app.core.errors import BusinessError


def configure_http(app: FastAPI):
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = "req_" + uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def error_response(request: Request, status: int, code: str, message: str, details: dict | None = None):
        body = s.ErrorResponse(
            error=s.ApiError(code=code, message=message, details=details or {}),
            request_id=request.state.request_id,
        )
        return JSONResponse(
            status_code=status,
            content=body.model_dump(mode="json"),
            headers={"X-Request-ID": body.request_id},
        )

    @app.exception_handler(BusinessError)
    async def business_error(request: Request, exc: BusinessError):
        return error_response(request, exc.status, exc.code, exc.message)

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
