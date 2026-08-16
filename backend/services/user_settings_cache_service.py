# Copyright (c) 2026 徐泽宇
"""Redis cache for per-user settings overrides (036).

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

logger = logging.getLogger(__name__)

CACHE_TTL_SEC = 3600
LOCAL_FALLBACK_TTL_SEC = 30.0

_lock = threading.Lock()
_local_cache: dict[int, tuple[float, dict[str, str]]] = {}


def _cache_key(user_id: int) -> str:
    return f"filex:user_settings:{user_id}"


def enabled() -> bool:
    return bool(REDIS_URL)


def _get_client():
    if not REDIS_URL:
        return None
    import redis

    return redis.from_url(REDIS_URL, decode_responses=True)


def _set_local(user_id: int, overrides: dict[str, str]) -> None:
    with _lock:
        _local_cache[user_id] = (time.time(), dict(overrides))


def _get_local_if_fresh(user_id: int) -> dict[str, str] | None:
    with _lock:
        entry = _local_cache.get(user_id)
        if entry is None:
            return None
        ts, overrides = entry
        if time.time() - ts < LOCAL_FALLBACK_TTL_SEC:
            return dict(overrides)
        return None


def _write_redis(user_id: int, overrides: dict[str, str]) -> None:
    client = _get_client()
    if client is None:
        return
    payload = json.dumps({"overrides": overrides}, ensure_ascii=False)
    try:
        client.set(_cache_key(user_id), payload, ex=CACHE_TTL_SEC)
    except Exception:
        logger.exception("user_settings_cache_redis_set_failed user_id=%s", user_id)


def invalidate_user_settings_cache(user_id: int) -> None:
    with _lock:
        _local_cache.pop(user_id, None)
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(_cache_key(user_id))
    except Exception:
        logger.exception("user_settings_cache_redis_delete_failed user_id=%s", user_id)


def _load_overrides_from_db(db: Session, user_id: int) -> dict[str, str]:
    from models.user_setting import UserSetting
    from services.user_setting_service import USER_SETTING_KEYS

    rows = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.setting_key.in_(USER_SETTING_KEYS))
        .all()
    )
    return {r.setting_key: r.value for r in rows}


def warm_user_settings_cache(db: Session, user_id: int) -> dict[str, str]:
    overrides = _load_overrides_from_db(db, user_id)
    _set_local(user_id, overrides)
    _write_redis(user_id, overrides)
    return overrides


def get_cached_user_overrides(db: Session, user_id: int) -> dict[str, str]:
    """Redis → 进程内 fallback → DB 加载并回填。"""
    if enabled():
        client = _get_client()
        if client is not None:
            try:
                raw = client.get(_cache_key(user_id))
                if raw:
                    data: dict[str, Any] = json.loads(raw)
                    overrides = dict(data.get("overrides") or {})
                    _set_local(user_id, overrides)
                    return overrides
            except json.JSONDecodeError:
                logger.warning("user_settings_cache_invalid_json user_id=%s", user_id)
            except Exception:
                logger.exception("user_settings_cache_redis_get_failed user_id=%s", user_id)

    local = _get_local_if_fresh(user_id)
    if local is not None:
        return local

    return warm_user_settings_cache(db, user_id)
