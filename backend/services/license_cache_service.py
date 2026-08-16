# Copyright (c) 2026 徐泽宇
"""Redis cache for FileX license status (021).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from config import REDIS_URL
from services.license_service import LicenseStatus, get_license_status

logger = logging.getLogger(__name__)

STATUS_KEY = "filex:license:status"
INVALID_TTL_SEC = 300
MAX_TTL_SEC = 86400
LOCAL_FALLBACK_TTL_SEC = 30.0

_lock = threading.Lock()
_local_cache: tuple[float, LicenseStatus] | None = None


def enabled() -> bool:
    return bool(REDIS_URL)


def _get_client():
    if not REDIS_URL:
        return None
    import redis

    return redis.from_url(REDIS_URL, decode_responses=True)


def _ttl_for_status(status: LicenseStatus) -> int:
    if not status.valid:
        return INVALID_TTL_SEC
    if status.expires_at is None:
        return MAX_TTL_SEC
    from utils.timezone import beijing_now

    now = beijing_now()
    exp = status.expires_at
    if exp.tzinfo is None:
        from utils.timezone import BEIJING_TZ

        exp = exp.replace(tzinfo=BEIJING_TZ)
    seconds = int((exp - now).total_seconds())
    if seconds <= 0:
        return INVALID_TTL_SEC
    return min(seconds, MAX_TTL_SEC)


def _set_local(status: LicenseStatus) -> None:
    global _local_cache
    with _lock:
        _local_cache = (time.time(), status)


def _get_local_if_fresh() -> LicenseStatus | None:
    global _local_cache
    with _lock:
        if _local_cache is None:
            return None
        ts, status = _local_cache
        if time.time() - ts < LOCAL_FALLBACK_TTL_SEC:
            return status
        return None


def _write_redis(status: LicenseStatus) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(STATUS_KEY, json.dumps(status.to_dict(), ensure_ascii=False), ex=_ttl_for_status(status))
    except Exception:
        logger.exception("license_cache_redis_set_failed")


def invalidate_license_cache() -> None:
    global _local_cache
    with _lock:
        _local_cache = None
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(STATUS_KEY)
    except Exception:
        logger.exception("license_cache_redis_delete_failed")


def warm_license_cache(db: Session) -> LicenseStatus:
    status = get_license_status(db)
    _set_local(status)
    _write_redis(status)
    return status


def get_cached_status(db: Session) -> LicenseStatus:
    """Redis → 进程内 fallback → DB 计算并回填。"""
    if enabled():
        client = _get_client()
        if client is not None:
            try:
                raw = client.get(STATUS_KEY)
                if raw:
                    data: dict[str, Any] = json.loads(raw)
                    status = LicenseStatus.from_dict(data)
                    _set_local(status)
                    return status
            except json.JSONDecodeError:
                logger.warning("license_cache_invalid_json")
            except Exception:
                logger.exception("license_cache_redis_get_failed")

    local = _get_local_if_fresh()
    if local is not None:
        return local

    status = get_license_status(db)
    _set_local(status)
    _write_redis(status)
    return status
