# Copyright (c) 2026 徐泽宇
"""kb.docling consumer retry boundary tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


SIDECAR_DIR = Path(__file__).resolve().parents[2] / "docker" / "docling-sidecar"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))
SIDECAR_FILE = SIDECAR_DIR / "mq_consumer.py"
SPEC = importlib.util.spec_from_file_location("docling_mq_consumer_under_test", SIDECAR_FILE)
assert SPEC is not None and SPEC.loader is not None
docling_mq_consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(docling_mq_consumer)


def test_docling_normalize_file_path_maps_app_uploads(monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", "/uploads")
    assert docling_mq_consumer._normalize_file_path("/app/uploads/1/doc.pdf") == "/uploads/1/doc.pdf"


def test_docling_is_retryable_classification():
    assert docling_mq_consumer._is_retryable(RuntimeError("cli")) is True
    assert docling_mq_consumer._is_retryable(ValueError("empty")) is False


def test_docling_on_message_nack_retryable(monkeypatch):
    monkeypatch.setenv("DOCLING_MQ_MAX_RETRIES", "2")
    ch = MagicMock()
    method = MagicMock(delivery_tag=1, redelivered=False)
    props = MagicMock(reply_to="reply-q", correlation_id="cid-1", headers={})
    body = json.dumps({"file_path": "/x.pdf", "file_id": 1}).encode()

    with patch.object(docling_mq_consumer, "_handle_message", side_effect=RuntimeError("transient")):
        docling_mq_consumer._on_message(ch, method, props, body)

    ch.basic_nack.assert_called_once_with(delivery_tag=1, requeue=True)
    ch.basic_ack.assert_not_called()


def test_docling_on_message_ack_permanent_error():
    ch = MagicMock()
    method = MagicMock(delivery_tag=2, redelivered=False)
    props = MagicMock(reply_to="reply-q", correlation_id="cid-2", headers={})
    body = json.dumps({"file_path": "/x.pdf"}).encode()

    with patch.object(docling_mq_consumer, "_handle_message", side_effect=ValueError("bad pdf")):
        docling_mq_consumer._on_message(ch, method, props, body)

    ch.basic_ack.assert_called_once_with(delivery_tag=2)
    ch.basic_nack.assert_not_called()
    payload = json.loads(ch.basic_publish.call_args.kwargs["body"].decode())
    assert payload["ok"] is False


def test_docling_on_message_ack_when_max_retries_exhausted(monkeypatch):
    monkeypatch.setenv("DOCLING_MQ_MAX_RETRIES", "2")
    ch = MagicMock()
    method = MagicMock(delivery_tag=3, redelivered=True)
    props = MagicMock(
        reply_to="reply-q",
        correlation_id="cid-3",
        headers={"x-death": [{"queue": "kb.docling", "count": 2}]},
    )
    body = json.dumps({"file_path": "/x.pdf", "file_id": 1}).encode()

    with patch.object(docling_mq_consumer, "_handle_message", side_effect=RuntimeError("transient")):
        docling_mq_consumer._on_message(ch, method, props, body)

    ch.basic_ack.assert_called_once_with(delivery_tag=3)
    ch.basic_nack.assert_not_called()
    payload = json.loads(ch.basic_publish.call_args.kwargs["body"].decode())
    assert payload["ok"] is False
    assert payload["error"] == "docling_parse_failed"


def test_docling_retry_count_ignores_other_queue_xdeath():
    method = MagicMock(redelivered=True)
    props = MagicMock(headers={"x-death": [{"queue": "kb.mineru", "count": 99}]})

    assert docling_mq_consumer._retry_count(method, props) == 1
