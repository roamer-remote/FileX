# Copyright (c) 2026 徐泽宇
"""Redis client utility for system-wide caching.

Authors:
    徐泽宇
"""

from __future__ import annotations

import logging

from config import REDIS_URL

logger = logging.getLogger(__name__)

_client = None


def get_redis():
    """Return a shared Redis client (decode_responses=True), or None if unavailable."""
    global _client
    if not REDIS_URL:
        return None
    try:
        import redis
        if _client is not None:
            try:
                _client.ping()
                return _client
            except Exception:
                _client = None
        _client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        _client.ping()
        return _client
    except Exception:
        logger.warning("redis_unavailable")
        _client = None
        return None


def redis_enabled() -> bool:
    return bool(REDIS_URL)


# Shared key prefix
KEY_PREFIX = "filex:"

# Cache keys
AGENT_SKILL_INSTALL_PROMPT_KEY = f"{KEY_PREFIX}agent_skill_install_prompt"
AGENT_SKILL_INSTALL_PROMPT_GEN_KEY = f"{KEY_PREFIX}agent_skill_install_prompt:gen"
AGENT_SKILL_INSTALL_PROMPT_TTL = 3600  # 1 hour
