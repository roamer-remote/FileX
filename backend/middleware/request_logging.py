# Copyright (c) 2026 徐泽宇
"""HTTP 请求结构化日志与 X-Request-ID 关联。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from logging_setup import http_access_via_app

log = structlog.get_logger("filex.http")

_SKIP_PATHS = frozenset({"/health", "/favicon.ico"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件 ASGI 中间件。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-18
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        if not http_access_via_app():
            return await call_next(request)

        path = request.url.path
        if path in _SKIP_PATHS or path.startswith("/assets/"):
            return await call_next(request)

        request_id = (request.headers.get("X-Request-ID") or "").strip() or str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        client = request.client.host if request.client else None
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log.exception(
                "http_request_failed",
                method=request.method,
                path=path,
                client=client,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            raise
        else:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log_method = log.warning if status_code >= 400 else log.info
            log_method(
                "http_request",
                method=request.method,
                path=path,
                client=client,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            response.headers["X-Request-ID"] = request_id
            return response
