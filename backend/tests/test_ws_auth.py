"""Tests for WebSocket first-frame authentication."""

from __future__ import annotations

import json

import pytest
from starlette.websockets import WebSocketDisconnect

from messaging.ws_auth import WS_AUTH_TYPE, _token_from_auth_frame, resolve_ws_user


class TestTokenFromAuthFrame:
    def test_json_auth(self):
        raw = json.dumps({"type": WS_AUTH_TYPE, "token": "abc123"})
        assert _token_from_auth_frame(raw) == "abc123"

    def test_plain_token(self):
        assert _token_from_auth_frame("  plain-token  ") == "plain-token"

    def test_wrong_type(self):
        raw = json.dumps({"type": "ping", "token": "x"})
        assert _token_from_auth_frame(raw) is None

    def test_empty(self):
        assert _token_from_auth_frame("") is None


@pytest.mark.asyncio
async def test_resolve_ws_user_rejects_bad_auth_frame():
    from starlette.testclient import TestClient

    from main import app

    client = TestClient(app)
    with client.websocket_connect("/api/ws/kb-index") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": "invalid-token"}))
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
        assert exc.value.code == 4401
