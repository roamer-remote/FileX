# Copyright (c) 2026 徐泽宇
"""In-process WebSocket connections for KB index status push.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

from fastapi import WebSocket

from messaging.kb_ws_notify_buffer import kb_ws_notify_replay_buffer

logger = logging.getLogger(__name__)

_METRIC_KEYS = (
    "ws_connections_active",
    "notify_broadcast_attempted",
    "notify_broadcast_delivered",
    "notify_broadcast_dropped_no_conn",
    "notify_broadcast_send_failed",
)


class KbIndexConnectionManager:
    """资料库索引connection管理器 管理器。"""

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._metrics_lock = threading.Lock()
        self._metrics: dict[str, int] = {k: 0 for k in _METRIC_KEYS}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def get_kb_ws_notify_metrics(self) -> dict[str, int]:
        with self._metrics_lock:
            return dict(self._metrics)

    def _inc_metric(self, key: str, delta: int = 1) -> None:
        with self._metrics_lock:
            self._metrics[key] = self._metrics.get(key, 0) + delta

    def _log_dropped(self, user_id: int, payload: dict[str, Any]) -> None:
        logger.info(
            "kb ws notify dropped (no connection) user_id=%s file_id=%s event_type=%s",
            user_id,
            payload.get("file_id"),
            payload.get("type"),
        )

    async def connect(self, user_id: int, websocket: WebSocket, *, already_accepted: bool = False) -> None:
        if not already_accepted:
            await websocket.accept()
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)
        self._inc_metric("ws_connections_active")

        for event in kb_ws_notify_replay_buffer.snapshot(user_id):
            try:
                replay_event = {**event, "_replay": True}
                await websocket.send_text(json.dumps(replay_event, ensure_ascii=False))
            except Exception:
                await self.disconnect(user_id, websocket)
                return

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        removed = False
        async with self._lock:
            conns = self._connections.get(user_id)
            if not conns:
                return
            if websocket in conns:
                removed = True
            conns.discard(websocket)
            if not conns:
                del self._connections[user_id]
        if removed:
            self._inc_metric("ws_connections_active", -1)

    async def broadcast(self, user_id: int, payload: dict[str, Any]) -> int:
        async with self._lock:
            conns = list(self._connections.get(user_id, set()))
        if not conns:
            return 0
        text = json.dumps(payload, ensure_ascii=False)
        dead: list[WebSocket] = []
        delivered = 0
        for ws in conns:
            try:
                await ws.send_text(text)
                delivered += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(user_id, ws)
        return delivered

    async def _broadcast_with_metrics(self, user_id: int, payload: dict[str, Any]) -> None:
        count = await self.broadcast(user_id, payload)
        if count > 0:
            self._inc_metric("notify_broadcast_delivered")
        else:
            self._inc_metric("notify_broadcast_send_failed")

    def broadcast_sync(self, user_id: int, payload: dict[str, Any]) -> None:
        self._inc_metric("notify_broadcast_attempted")
        loop = self._loop
        no_delivery = (
            loop is None
            or not loop.is_running()
            or user_id not in self._connections
            or not self._connections[user_id]
        )
        if no_delivery:
            self._inc_metric("notify_broadcast_dropped_no_conn")
            self._log_dropped(user_id, payload)
            return
        asyncio.run_coroutine_threadsafe(
            self._broadcast_with_metrics(user_id, payload), loop
        )


kb_index_ws_manager = KbIndexConnectionManager()
