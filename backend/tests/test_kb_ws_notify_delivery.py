"""054: KB WebSocket notify metrics, replay buffer, connect replay."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from messaging.kb_ws_notify_buffer import KbWsNotifyReplayBuffer
from messaging.ws_manager import KbIndexConnectionManager


def _sample_event(file_id: int = 42) -> dict:
    return {
        "type": "kb_extract_updated",
        "file_id": file_id,
        "extract_status": "ready",
    }


class TestKbWsNotifyReplayBuffer:
    def test_append_and_snapshot(self):
        buf = KbWsNotifyReplayBuffer()
        event = _sample_event()
        buf.append(1, event)
        assert buf.snapshot(1) == [event]

    def test_evicts_beyond_max_per_user(self):
        buf = KbWsNotifyReplayBuffer(max_per_user=32, ttl_sec=600.0)
        for i in range(40):
            buf.append(7, _sample_event(i))
        snap = buf.snapshot(7)
        assert len(snap) == 32
        assert snap[0]["file_id"] == 8
        assert snap[-1]["file_id"] == 39

    def test_ttl_expired_not_replayed(self, monkeypatch):
        buf = KbWsNotifyReplayBuffer(max_per_user=32, ttl_sec=600.0)
        t = [1000.0]

        monkeypatch.setattr("messaging.kb_ws_notify_buffer.time.monotonic", lambda: t[0])
        buf.append(1, _sample_event(1))
        t[0] += 601.0
        assert buf.snapshot(1) == []


    def test_ttl_eviction_removes_empty_user_key(self, monkeypatch):
        buf = KbWsNotifyReplayBuffer(ttl_sec=600.0)
        t = [1000.0]
        monkeypatch.setattr("messaging.kb_ws_notify_buffer.time.monotonic", lambda: t[0])
        buf.append(1, _sample_event(1))
        assert 1 in buf._buffers
        t[0] += 601.0
        assert buf.snapshot(1) == []
        assert 1 not in buf._buffers


class TestKbIndexConnectionManagerMetrics:
    def test_broadcast_sync_dropped_when_loop_not_running(self):
        mgr = KbIndexConnectionManager()
        loop = asyncio.new_event_loop()
        try:
            mgr.bind_loop(loop)
            mgr.broadcast_sync(10, _sample_event())
            m = mgr.get_kb_ws_notify_metrics()
            assert m["notify_broadcast_attempted"] == 1
            assert m["notify_broadcast_dropped_no_conn"] == 1
            assert m["notify_broadcast_delivered"] == 0
        finally:
            loop.close()


    @pytest.mark.asyncio
    async def test_broadcast_sync_dropped_when_loop_running_no_connection(self):
        mgr = KbIndexConnectionManager()
        mgr.bind_loop(asyncio.get_running_loop())
        mgr.broadcast_sync(10, _sample_event())
        m = mgr.get_kb_ws_notify_metrics()
        assert m["notify_broadcast_attempted"] == 1
        assert m["notify_broadcast_dropped_no_conn"] == 1
        assert m["notify_broadcast_delivered"] == 0

    @pytest.mark.asyncio
    async def test_broadcast_delivered_with_connection(self):
        mgr = KbIndexConnectionManager()
        mgr.bind_loop(asyncio.get_running_loop())
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        await mgr.connect(5, ws, already_accepted=True)
        count = await mgr.broadcast(5, _sample_event())
        assert count == 1
        m = mgr.get_kb_ws_notify_metrics()
        assert m["ws_connections_active"] == 1

    @pytest.mark.asyncio
    async def test_connect_replays_buffered_events(self):
        buf = KbWsNotifyReplayBuffer()
        mgr = KbIndexConnectionManager()
        event = _sample_event(99)
        buf.append(3, event)
        ws = AsyncMock()
        ws.send_text = AsyncMock()

        import messaging.ws_manager as ws_mod

        original = ws_mod.kb_ws_notify_replay_buffer
        ws_mod.kb_ws_notify_replay_buffer = buf
        try:
            await mgr.connect(3, ws, already_accepted=True)
        finally:
            ws_mod.kb_ws_notify_replay_buffer = original

        ws.send_text.assert_called_once()
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["file_id"] == 99
        assert sent["_replay"] is True


def test_on_notify_appends_buffer_before_broadcast(monkeypatch):
    from messaging import kb_index_notify as mod

    appended: list[tuple[int, dict]] = []
    broadcast_calls: list[tuple[int, dict]] = []

    class FakeBuffer:
        def append(self, user_id: int, event: dict) -> None:
            appended.append((user_id, event))

    monkeypatch.setattr(mod, "kb_ws_notify_replay_buffer", FakeBuffer())

    class FakeMgr:
        def broadcast_sync(self, user_id: int, event: dict) -> None:
            broadcast_calls.append((user_id, event))

    monkeypatch.setattr(mod, "kb_index_ws_manager", FakeMgr())
    monkeypatch.setattr(mod, "request_refresh", lambda: None, raising=False)

    class Method:
        delivery_tag = 1

    class Ch:
        def basic_ack(self, delivery_tag: int) -> None:
            pass

    body = json.dumps(
        {
            "user_id": 2,
            "type": "kb_index_updated",
            "file_id": 11,
            "index_status": "ready",
        }
    ).encode()
    mod._on_notify(Ch(), Method(), None, body)
    assert appended
    assert broadcast_calls
    assert appended[0][0] == broadcast_calls[0][0] == 2


def test_admin_kb_ws_notify_metrics(client, admin_jwt_token, monkeypatch):
    metrics = {
        "ws_connections_active": 2,
        "notify_broadcast_attempted": 10,
        "notify_broadcast_delivered": 8,
        "notify_broadcast_dropped_no_conn": 1,
        "notify_broadcast_send_failed": 0,
    }
    monkeypatch.setattr(
        "routers.admin.kb_index_ws_manager.get_kb_ws_notify_metrics",
        lambda: metrics,
    )
    r = client.get(
        "/api/admin/kb-ws-notify-metrics",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert r.status_code == 200
    assert r.json() == {
        "wsConnectionsActive": 2,
        "notifyBroadcastAttempted": 10,
        "notifyBroadcastDelivered": 8,
        "notifyBroadcastDroppedNoConn": 1,
        "notifyBroadcastSendFailed": 0,
    }
