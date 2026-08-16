# Copyright (c) 2026 徐泽宇
"""License 全局拦截（021）：无效授权时阻断 /api/* 业务请求。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config import OPENAPI_ENABLED
from database import SessionLocal
from services.license_cache_service import get_cached_status
from services.license_service import license_http_body

# FR-304 allowlist；api-key-status 需到达 handler 以返回 200 + license_expired（SC-005）
_ALLOWLIST_EXACT = frozenset(
    {
        "/api/health",
        "/api/meta/runtime",
        "/api/external/api-key-status",
        # 044: Insavlo webhook 写回必须越过 License 闸（SC-009）
        "/api/webhooks/insavlo/document-process",
    }
)
_ALLOWLIST_PREFIXES = ("/api/license/",)


def is_license_allowlisted(path: str) -> bool:
    if path in _ALLOWLIST_EXACT:
        return True
    if any(path.startswith(p) for p in _ALLOWLIST_PREFIXES):
        return True
    if OPENAPI_ENABLED and path in ("/openapi.json", "/docs", "/redoc", "/doc"):
        return True
    return False


class LicenseMiddleware(BaseHTTPMiddleware):
    """授权中间件 ASGI 中间件。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-10
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not path.startswith("/api/") or is_license_allowlisted(path):
            return await call_next(request)

        db = SessionLocal()
        try:
            status = get_cached_status(db)
        finally:
            db.close()

        if not status.valid:
            return JSONResponse(status_code=403, content=license_http_body(status))
        return await call_next(request)
