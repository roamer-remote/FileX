# Copyright (c) 2026 徐泽宇
"""Redis-backed read of the pdf-inspector runtime switch (system parameter table).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import threading
import time

from config import REDIS_URL

logger = logging.getLogger(__name__)

CACHE_TTL_SEC = 300
LOCAL_FALLBACK_TTL_SEC = 30.0
CACHE_KEY = "filex:pdf_inspector_enabled"

_lock = threading.Lock()
_local_cache: tuple[float, bool] | None = None


def enabled() -> bool:
    return bool(REDIS_URL)


def _get_client():
    if not REDIS_URL:
        return None
    import redis

    return redis.from_url(REDIS_URL, decode_responses=True)


def _set_local(value: bool) -> None:
    global _local_cache
    with _lock:
        _local_cache = (time.time(), value)


def _get_local_if_fresh() -> bool | None:
    global _local_cache
    with _lock:
        entry = _local_cache
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts < LOCAL_FALLBACK_TTL_SEC:
            return value
        return None


def _write_redis(value: bool) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(CACHE_KEY, "true" if value else "false", ex=CACHE_TTL_SEC)
    except Exception:
        logger.exception("pdf_inspector_switch_redis_set_failed")


def invalidate_pdf_inspector_switch_cache() -> None:
    """Clear in-process + Redis switch cache (called on admin settings save)."""
    global _local_cache
    with _lock:
        _local_cache = None
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(CACHE_KEY)
    except Exception:
        logger.exception("pdf_inspector_switch_redis_delete_failed")


def _load_from_db(db) -> bool:
    if db is None:
        return False
    try:
        from services.system_setting_service import get_kb_pdf_inspector_enabled

        return get_kb_pdf_inspector_enabled(db)
    except Exception:
        logger.exception("pdf_inspector_switch_db_load_failed")
        return False


def get_pdf_inspector_enabled(db=None) -> bool:
    """Redis → 进程内 fallback → DB 加载并回填。默认关闭。"""
    if enabled():
        client = _get_client()
        if client is not None:
            try:
                raw = client.get(CACHE_KEY)
                if raw is not None:
                    value = str(raw).strip().lower() in ("1", "true", "yes", "on")
                    _set_local(value)
                    return value
            except Exception:
                logger.exception("pdf_inspector_switch_redis_get_failed")

    local = _get_local_if_fresh()
    if local is not None:
        return local

    value = _load_from_db(db)
    _set_local(value)
    _write_redis(value)
    return value
