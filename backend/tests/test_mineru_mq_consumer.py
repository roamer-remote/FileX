# Copyright (c) 2026 徐泽宇
"""032 PR-A: kb.mineru consumer ack/nack semantics."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SIDECAR_DIR = Path(__file__).resolve().parents[2] / "docker" / "mineru-sidecar"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))

from mq_consumer import _is_retryable, _normalize_file_path, _on_message  # noqa: E402


def test_normalize_file_path_maps_app_uploads(monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", "/uploads")
    assert _normalize_file_path("/app/uploads/1/2026-06/doc.pdf") == (
        "/uploads/1/2026-06/doc.pdf"
    )
    assert _normalize_file_path("/uploads/1/doc.pdf") == "/uploads/1/doc.pdf"


def test_is_retryable_classification():
    assert _is_retryable(RuntimeError("cli")) is True
    assert _is_retryable(ValueError("empty")) is False
    assert _is_retryable(FileNotFoundError("x")) is False


@patch("mq_consumer._handle_message", side_effect=RuntimeError("transient"))
def test_on_message_nack_retryable(mock_handle, monkeypatch):
    monkeypatch.setenv("MINERU_MQ_MAX_RETRIES", "2")
    ch = MagicMock()
    method = MagicMock(delivery_tag=1, redelivered=False)
    props = MagicMock(reply_to="reply-q", correlation_id="cid-1", headers={})
    body = json.dumps({"file_path": "/x.pdf", "file_id": 1}).encode()

    _on_message(ch, method, props, body)

    ch.basic_nack.assert_called_once_with(delivery_tag=1, requeue=True)
    ch.basic_ack.assert_not_called()
    ch.basic_publish.assert_not_called()


@patch("mq_consumer._handle_message", side_effect=ValueError("bad pdf"))
def test_on_message_ack_permanent_error(mock_handle):
    ch = MagicMock()
    method = MagicMock(delivery_tag=2, redelivered=False)
    props = MagicMock(reply_to="reply-q", correlation_id="cid-2", headers={})
    body = json.dumps({"file_path": "/x.pdf"}).encode()

    _on_message(ch, method, props, body)

    ch.basic_ack.assert_called_once_with(delivery_tag=2)
    ch.basic_nack.assert_not_called()
    assert ch.basic_publish.call_count == 1
    payload = json.loads(ch.basic_publish.call_args.kwargs["body"].decode())
    assert payload["ok"] is False

@patch("mq_consumer._handle_message", side_effect=RuntimeError("transient"))
def test_on_message_ack_when_max_retries_exhausted(mock_handle, monkeypatch):
    monkeypatch.setenv("MINERU_MQ_MAX_RETRIES", "2")
    ch = MagicMock()
    method = MagicMock(delivery_tag=3, redelivered=True)
    props = MagicMock(
        reply_to="reply-q",
        correlation_id="cid-3",
        headers={"x-death": [{"queue": "kb.mineru", "count": 2}]},
    )
    body = json.dumps({"file_path": "/x.pdf", "file_id": 1}).encode()

    _on_message(ch, method, props, body)

    ch.basic_ack.assert_called_once_with(delivery_tag=3)
    ch.basic_nack.assert_not_called()
    payload = json.loads(ch.basic_publish.call_args.kwargs["body"].decode())
    assert payload["ok"] is False



@patch("mq_consumer._handle_message")
def test_on_message_processes_data_events_during_long_parse(mock_handle):
    import time

    def slow_handle(_body):
        time.sleep(0.05)
        return {"markdown": "# cached-path"}

    mock_handle.side_effect = slow_handle
    conn = MagicMock()
    event_calls: list[float] = []
    conn.process_data_events = lambda time_limit=1: event_calls.append(time_limit)
    ch = MagicMock()
    ch.connection = conn
    method = MagicMock(delivery_tag=4, redelivered=False)
    props = MagicMock(reply_to="reply-q", correlation_id="cid-4", headers={})
    body = json.dumps({"file_path": "/x.pdf", "file_id": 2}).encode()

    _on_message(ch, method, props, body)

    assert len(event_calls) >= 1
    assert all(t == 1 for t in event_calls)
    ch.basic_ack.assert_called_once_with(delivery_tag=4)


@patch("mq_consumer._handle_message")
def test_on_message_waits_for_worker_after_connection_lost(mock_handle):
    import time

    started = time.monotonic()

    def slow_handle(_body):
        time.sleep(0.05)
        return {"markdown": "# done-after-disconnect"}

    mock_handle.side_effect = slow_handle
    conn = MagicMock()
    calls = {"n": 0}

    def flaky_events(time_limit=1):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionResetError("stream lost")

    conn.process_data_events = flaky_events
    ch = MagicMock()
    ch.connection = conn
    method = MagicMock(delivery_tag=5, redelivered=False)
    props = MagicMock(reply_to="reply-q", correlation_id="cid-5", headers={})
    body = json.dumps({"file_path": "/x.pdf", "file_id": 3}).encode()

    _on_message(ch, method, props, body)

    assert time.monotonic() - started >= 0.04
    ch.basic_nack.assert_called_once_with(delivery_tag=5, requeue=True)
    ch.basic_ack.assert_not_called()
