# Copyright (c) 2026 徐泽宇
"""WebSocket connections for MQ status (per-user personalized payloads).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket


class MqMonitorConnectionManager:
    """消息队列monitorconnection管理器 管理器。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-18
    """
    def __init__(self) -> None:
        self._connections: dict[WebSocket, int] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def has_connections(self) -> bool:
        return bool(self._connections)

    async def connect(self, websocket: WebSocket, user_id: int, *, already_accepted: bool = False) -> None:
        if not already_accepted:
            await websocket.accept()
        async with self._lock:
            self._connections[websocket] = user_id

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(websocket, None)

    async def send_to(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(payload, ensure_ascii=False))

    async def broadcast_personalized(self) -> None:
        from database import SessionLocal
        from models.user import User
        from services.rabbitmq_status_service import get_mq_status, to_mq_status_event

        async with self._lock:
            items = list(self._connections.items())
        if not items:
            return

        db = SessionLocal()
        dead: list[WebSocket] = []
        try:
            from services.rabbitmq_retry_dlq_snapshot_service import warm_retry_dlq_snapshot

            warm_retry_dlq_snapshot(db)
            for ws, user_id in items:
                user = db.query(User).filter(User.id == user_id).first()
                status = get_mq_status(viewer=user) if user else get_mq_status(viewer=None)
                try:
                    await self.send_to(ws, to_mq_status_event(status))
                except Exception:
                    dead.append(ws)
        finally:
            db.close()
        for ws in dead:
            await self.disconnect(ws)

    def broadcast_personalized_sync(self) -> None:
        loop = self._loop
        if loop is None or not loop.is_running() or not self.has_connections():
            return
        asyncio.run_coroutine_threadsafe(self.broadcast_personalized(), loop)


mq_ws_manager = MqMonitorConnectionManager()
