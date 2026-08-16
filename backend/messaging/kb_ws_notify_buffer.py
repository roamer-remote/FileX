# Copyright (c) 2026 徐泽宇
"""In-memory replay buffer for KB WebSocket notify events (054)."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _BufferedEvent:
    event: dict[str, Any]
    enqueued_at: float


class KbWsNotifyReplayBuffer:
    """Per-user bounded deque of recent WS events for connect replay.

    Keys are removed from ``_buffers`` when a user's deque becomes empty after
    TTL eviction (not on connect replay — buffer is shared across tabs).
    """

    def __init__(self, *, max_per_user: int = 32, ttl_sec: float = 600.0) -> None:
        self._max_per_user = max_per_user
        self._ttl_sec = ttl_sec
        self._buffers: dict[int, deque[_BufferedEvent]] = {}
        self._lock = threading.Lock()

    def append(self, user_id: int, event: dict[str, Any]) -> None:
        now = time.monotonic()
        with self._lock:
            dq = self._buffers.setdefault(user_id, deque())
            dq.append(_BufferedEvent(event=event, enqueued_at=now))
            self._evict_expired_locked(user_id, dq, now)
            while len(dq) > self._max_per_user:
                evicted = dq.popleft()
                logger.warning(
                    "kb ws notify replay buffer evicted oldest user_id=%s file_id=%s event_type=%s",
                    user_id,
                    evicted.event.get("file_id"),
                    evicted.event.get("type"),
                )

    def snapshot(self, user_id: int) -> list[dict[str, Any]]:
        now = time.monotonic()
        with self._lock:
            dq = self._buffers.get(user_id)
            if not dq:
                return []
            self._evict_expired_locked(user_id, dq, now)
            return [item.event for item in dq]

    def _evict_expired_locked(
        self, user_id: int, dq: deque[_BufferedEvent], now: float
    ) -> None:
        while dq and (now - dq[0].enqueued_at) > self._ttl_sec:
            dq.popleft()
        if not dq:
            self._buffers.pop(user_id, None)


kb_ws_notify_replay_buffer = KbWsNotifyReplayBuffer()
