# Copyright (c) 2026 徐泽宇
"""070: Docling MQ RPC client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from messaging.kb_docling_rpc import DoclingRpcTimeout, call_docling_extract
from models.file import File as FileModel
from services.extract.providers.docling_provider import extract_docling


def test_call_docling_extract_success():
    captured = {}

    reply_payload = {
        "ok": True,
        "markdown": "# doc",
        "content_list": [{"type": "text", "text": "hi", "page_idx": 0}],
    }

    class FakeChannel:
        consumer_tags = ["tag-1"]

        def queue_declare(self, **_kwargs):
            result = MagicMock()
            result.method.queue = "reply-q"
            return result

        def basic_consume(self, queue, on_message_callback, auto_ack):
            captured["cb"] = on_message_callback

        def basic_publish(self, **_kwargs):
            captured["props"] = _kwargs.get("properties")
            props = MagicMock()
            props.correlation_id = captured["props"].correlation_id
            method = MagicMock()
            method.delivery_tag = 1
            captured["cb"](self, method, props, json.dumps(reply_payload).encode())

        def basic_ack(self, delivery_tag):
            return None

        def basic_cancel(self, _tag):
            return None

    fake_conn = MagicMock()
    fake_conn.is_open = True
    fake_conn.channel.return_value = FakeChannel()
    fake_conn.process_data_events = lambda time_limit=0: None

    with patch("messaging.kb_docling_rpc.open_blocking_connection", return_value=fake_conn):
        with patch("messaging.kb_docling_rpc.declare_kb_docling_topology"):
            result = call_docling_extract(
                job_id=1,
                file_id=9,
                file_path="/uploads/1/doc.pdf",
                original_name="doc.pdf",
            )

    assert result["markdown"] == "# doc"
    assert captured["props"].expiration == "600000"


def test_call_docling_extract_timeout():
    class FakeChannel:
        consumer_tags = ["tag-1"]

        def queue_declare(self, **_kwargs):
            result = MagicMock()
            result.method.queue = "reply-q"
            return result

        def basic_consume(self, **_kwargs):
            pass

        def basic_publish(self, **_kwargs):
            pass

        def basic_cancel(self, _tag):
            return None

    fake_conn = MagicMock()
    fake_conn.is_open = True
    fake_conn.channel.return_value = FakeChannel()

    with patch("messaging.kb_docling_rpc.open_blocking_connection", return_value=fake_conn):
        with patch("messaging.kb_docling_rpc.declare_kb_docling_topology"):
            with patch("messaging.kb_docling_rpc.KB_EXTRACT_DOCLING_TIMEOUT_SEC", 0.01):
                with pytest.raises(DoclingRpcTimeout):
                    call_docling_extract(
                        job_id=1,
                        file_id=9,
                        file_path="/x.pdf",
                        original_name="x.pdf",
                    )


@patch("services.extract.providers.docling_provider.KB_EXTRACT_DOCLING_USE_MQ", True)
@patch("messaging.kb_docling_rpc.call_docling_extract")
def test_extract_docling_mq_path(mock_rpc, regular_user, tmp_path):
    pdf = tmp_path / "mq.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        id=42,
        filename="mq.pdf",
        original_name="mq.pdf",
        file_path=str(pdf),
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    mock_rpc.return_value = {"ok": True, "markdown": "# from mq", "content_list": []}
    result = extract_docling(f, job_id=7)
    assert result.text == "# from mq"
    mock_rpc.assert_called_once()
    assert mock_rpc.call_args.kwargs["job_id"] == 7
