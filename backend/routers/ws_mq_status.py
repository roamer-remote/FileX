# Copyright (c) 2026 徐泽宇
"""WebSocket: MQ queue status — push on server-detected changes (authenticated users).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from database import SessionLocal
from messaging.mq_status_watcher import note_status_sent_global, request_refresh
from messaging.mq_ws_manager import mq_ws_manager
from messaging.ws_auth import resolve_ws_user
from services.rabbitmq_status_service import get_mq_status, to_mq_status_event

router = APIRouter()


@router.websocket("/mq-status")
async def mq_status_ws(websocket: WebSocket, token: str = ""):
    db = SessionLocal()
    try:
        auth = await resolve_ws_user(websocket, token, db)
        user = auth.user
        if not user or not user.is_active:
            if not auth.accepted:
                await websocket.accept()
            await websocket.close(code=4403 if user and not user.is_active else 4401, reason="Forbidden")
            return
    finally:
        db.close()

    await mq_ws_manager.connect(websocket, user.id, already_accepted=auth.accepted)
    try:
        status = get_mq_status(viewer=user)
        note_status_sent_global()
        await mq_ws_manager.send_to(websocket, to_mq_status_event(status))

        while True:
            raw = await websocket.receive_text()
            if raw.strip().lower() == "refresh":
                status = get_mq_status(viewer=user)
                note_status_sent_global()
                await mq_ws_manager.send_to(websocket, to_mq_status_event(status))
                request_refresh()
    except WebSocketDisconnect:
        pass
    finally:
        await mq_ws_manager.disconnect(websocket)
