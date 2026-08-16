# Copyright (c) 2026 徐泽宇
"""WebSocket: KB vector index status updates per user.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from database import SessionLocal
from messaging.ws_auth import resolve_ws_user
from messaging.ws_manager import kb_index_ws_manager

router = APIRouter()


@router.websocket("/kb-index")
async def kb_index_ws(websocket: WebSocket, token: str = ""):
    db = SessionLocal()
    try:
        auth = await resolve_ws_user(websocket, token, db)
        if not auth.user:
            if not auth.accepted:
                await websocket.accept()
            await websocket.close(code=4401, reason="Unauthorized")
            return
        user_id = auth.user.id
    finally:
        db.close()

    await kb_index_ws_manager.connect(user_id, websocket, already_accepted=auth.accepted)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await kb_index_ws_manager.disconnect(user_id, websocket)
