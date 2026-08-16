# Copyright (c) 2026 徐泽宇
"""WebSocket authentication: query ?token= (legacy) or first-frame JSON auth."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, WebSocket
from sqlalchemy.orm import Session

from middleware.auth import user_from_url_query_token
from models.user import User

WS_AUTH_TYPE = "auth"


@dataclass(frozen=True)
class WsAuthResult:
    user: User | None
    accepted: bool


def _token_from_auth_frame(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        if data.get("type") != WS_AUTH_TYPE:
            return None
        token = data.get("token")
        return token if isinstance(token, str) and token.strip() else None
    return text


async def resolve_ws_user(
    websocket: WebSocket,
    query_token: str,
    db: Session,
) -> WsAuthResult:
    """Resolve user from ?token= (legacy) or first text frame ``{"type":"auth","token":"..."}``."""
    if query_token.strip():
        try:
            user = user_from_url_query_token(query_token.strip(), db)
        except HTTPException:
            return WsAuthResult(user=None, accepted=False)
        return WsAuthResult(user=user, accepted=False)

    await websocket.accept()
    try:
        raw = await websocket.receive_text()
    except Exception:
        return WsAuthResult(user=None, accepted=True)

    token = _token_from_auth_frame(raw)
    if not token:
        return WsAuthResult(user=None, accepted=True)
    try:
        user = user_from_url_query_token(token, db)
    except HTTPException:
        return WsAuthResult(user=None, accepted=True)
    return WsAuthResult(user=user, accepted=True)
