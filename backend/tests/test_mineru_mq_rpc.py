# Copyright (c) 2026 徐泽宇
"""032 PR-A: MinerU MQ RPC client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from messaging.kb_mineru_rpc import MineruRpcTimeout, call_mineru_extract
from models.file import File as FileModel
from services.extract.providers.mineru_provider import extract_mineru
from tests.test_mineru_config_service import _cfg as _mineru_test_cfg


def test_call_mineru_extract_success():
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
    fake_conn.params.blocked_connection_timeout = None
    fake_conn.process_data_events = lambda time_limit=0: None

    with patch("messaging.kb_mineru_rpc.open_blocking_connection", return_value=fake_conn):
        with patch("messaging.kb_mineru_rpc.declare_kb_mineru_topology"):
            with patch("messaging.kb_mineru_rpc._resolve_rpc_timeouts", return_value=(900_000, 900.0, _mineru_test_cfg())):
                result = call_mineru_extract(
                    job_id=1,
                    file_id=9,
                    file_path="/uploads/1/doc.pdf",
                    original_name="doc.pdf",
                )

    assert result["markdown"] == "# doc"
    assert captured["props"].expiration == "900000"


def test_call_mineru_extract_timeout():
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
    fake_conn.params.blocked_connection_timeout = None

    with patch("messaging.kb_mineru_rpc.open_blocking_connection", return_value=fake_conn):
        with patch("messaging.kb_mineru_rpc.declare_kb_mineru_topology"):
            with patch("messaging.kb_mineru_rpc._resolve_rpc_timeouts", return_value=(10, 0.01, _mineru_test_cfg())):
                with pytest.raises(MineruRpcTimeout):
                    call_mineru_extract(
                        job_id=1,
                        file_id=9,
                        file_path="/x.pdf",
                        original_name="x.pdf",
                    )


@patch("services.extract.providers.mineru_provider.KB_EXTRACT_MINERU_USE_MQ", True)
@patch("messaging.kb_mineru_rpc.call_mineru_extract")
def test_extract_mineru_mq_path(mock_rpc, regular_user, tmp_path, monkeypatch):
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", True)
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
    result = extract_mineru(f, job_id=7)
    assert result.text == "# from mq"
    assert result.engine == "mineru"
    assert result.content_list == []
    call = mock_rpc.call_args
    assert call.args == ()
    assert call.kwargs["job_id"] == 7
    assert call.kwargs["file_id"] == 42
    assert call.kwargs["file_path"] == str(pdf)
    assert call.kwargs["original_name"] == "mq.pdf"
    assert call.kwargs["bypass_cache"] is False
    assert call.kwargs["db"] is None
    assert call.kwargs["gpu_scheduler"] is not None
    assert call.kwargs["gpu_context"].job_id == "7"


@patch("services.extract.providers.mineru_provider.KB_EXTRACT_MINERU_USE_MQ", True)
@patch("messaging.kb_mineru_rpc.call_mineru_extract")
def test_extract_mineru_mq_cpu_path_does_not_inject_scheduler(
    mock_rpc, regular_user, tmp_path, monkeypatch
):
    monkeypatch.setattr("config.GPU_SCHEDULER_ENABLED", False)
    pdf = tmp_path / "cpu.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        id=43,
        filename="cpu.pdf",
        original_name="cpu.pdf",
        file_path=str(pdf),
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    mock_rpc.return_value = {"ok": True, "markdown": "# from cpu mq", "content_list": []}

    result = extract_mineru(f, job_id=8)

    assert result.text == "# from cpu mq"
    call = mock_rpc.call_args
    assert call.kwargs["gpu_scheduler"] is None
    assert call.kwargs["gpu_context"] is None


def test_call_mineru_extract_bypass_cache_payload():
    captured = {}

    reply_payload = {"ok": True, "markdown": "# doc"}

    class FakeChannel:
        consumer_tags = ["tag-1"]

        def queue_declare(self, **_kwargs):
            result = MagicMock()
            result.method.queue = "reply-q"
            return result

        def basic_consume(self, queue, on_message_callback, auto_ack):
            captured["cb"] = on_message_callback

        def basic_publish(self, exchange, routing_key, body, properties=None, **_kwargs):
            captured["body"] = json.loads(body.decode())
            props = MagicMock()
            props.correlation_id = properties.correlation_id
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

    with patch("messaging.kb_mineru_rpc.open_blocking_connection", return_value=fake_conn):
        with patch("messaging.kb_mineru_rpc.declare_kb_mineru_topology"):
            with patch("messaging.kb_mineru_rpc._resolve_rpc_timeouts", return_value=(900_000, 900.0, _mineru_test_cfg())):
                call_mineru_extract(
                    job_id=2,
                    file_id=9,
                    file_path="/uploads/1/doc.pdf",
                    original_name="doc.pdf",
                    bypass_cache=True,
                )

    assert captured["body"]["bypass_cache"] is True
    assert captured["body"]["runtime_config_version"] == 1
    assert "runtime_config" in captured["body"]


@patch("messaging.kb_mineru_rpc.pdf_page_count", return_value=288)
def test_resolve_rpc_timeout_288_pages(mock_pages, db_session):
    from messaging.kb_mineru_rpc import _resolve_rpc_timeouts
    from services.mineru_config_service import MineruRuntimeConfig
    from services.system_setting_service import (
        KEY_MINERU_PAGE_CHUNK_ENABLED,
        KEY_MINERU_PAGE_CHUNK_PAGES,
        KEY_MINERU_PAGE_CHUNK_THRESHOLD,
        KEY_MINERU_PARSE_TIMEOUT_SEC,
        KEY_MINERU_RPC_TIMEOUT_SEC,
        update_settings,
    )

    update_settings(
        db_session,
        {
            KEY_MINERU_RPC_TIMEOUT_SEC: "900",
            KEY_MINERU_PARSE_TIMEOUT_SEC: "850",
            KEY_MINERU_PAGE_CHUNK_ENABLED: "true",
            KEY_MINERU_PAGE_CHUNK_THRESHOLD: "120",
            KEY_MINERU_PAGE_CHUNK_PAGES: "48",
        },
    )

    timeout_ms, effective_sec, cfg = _resolve_rpc_timeouts(
        db=db_session,
        file_path="/tmp/big.pdf",
    )
    assert isinstance(cfg, MineruRuntimeConfig)
    assert effective_sec >= 5220
    assert timeout_ms == int(effective_sec) * 1000
