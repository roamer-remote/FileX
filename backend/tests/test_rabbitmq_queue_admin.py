# Copyright (c) 2026 徐泽宇
"""Unit tests for MQ queue admin drain/delete logic (no live RabbitMQ).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from services import rabbitmq_queue_admin_service as svc


def test_parse_message_body_dlq_json():
    body = json.dumps({"job_id": 14, "last_error": "timed out"}).encode()
    job_id, last_error, preview = svc._parse_message_body(body)
    assert job_id == 14
    assert last_error == "timed out"
    assert "job_id" in preview


def test_mutate_delete_by_index():
    q = "kb.index.dlq"
    msgs = [
        (None, b'{"job_id": 1}'),
        (None, b'{"job_id": 14}'),
        (None, b'{"job_id": 14}'),
    ]

    def fake_drain(ch, queue_name, max_count=None):
        return list(msgs)

    mock_ch = MagicMock()
    mock_conn = MagicMock()
    mock_conn.is_open = True
    mock_conn.channel.return_value = mock_ch

    with (
        patch.object(svc, "open_blocking_connection", return_value=mock_conn),
        patch.object(svc, "declare_kb_index_topology"),
        patch.object(svc, "_drain_queue", side_effect=fake_drain),
        patch.object(svc, "_republish_queue") as repub,
    ):
        result = svc.mutate_queue_messages(q, index=1)

    assert result["removed"] == 1
    assert result["message_count"] == 2
    repub.assert_called_once()
    kept = repub.call_args[0][2]
    assert len(kept) == 2
    assert json.loads(kept[0][1])["job_id"] == 1
    assert json.loads(kept[1][1])["job_id"] == 14


def test_mutate_delete_all_by_job_id():
    q = "kb.index.dlq"
    msgs = [
        (None, b'{"job_id": 14}'),
        (None, b'{"job_id": 14}'),
        (None, b'{"job_id": 99}'),
    ]

    def fake_drain(ch, queue_name, max_count=None):
        return list(msgs)

    mock_ch = MagicMock()
    mock_conn = MagicMock()
    mock_conn.is_open = True
    mock_conn.channel.return_value = mock_ch

    with (
        patch.object(svc, "open_blocking_connection", return_value=mock_conn),
        patch.object(svc, "declare_kb_index_topology"),
        patch.object(svc, "_drain_queue", side_effect=fake_drain),
        patch.object(svc, "_republish_queue") as repub,
    ):
        result = svc.mutate_queue_messages(q, job_id=14)

    assert result["removed"] == 2
    assert result["message_count"] == 1
    kept = repub.call_args[0][2]
    assert json.loads(kept[0][1])["job_id"] == 99


def test_mutate_delete_by_job_ids_requires_exact_json_job_id():
    q = "kb.extract"
    msgs = [
        (None, b'{"job_id": 14}'),
        (None, b'{"job_id": 99}'),
        (None, b'{"file_id": 14}'),
        (None, b'not-json'),
    ]

    mock_ch = MagicMock()
    mock_conn = MagicMock()
    mock_conn.is_open = True
    mock_conn.channel.return_value = mock_ch

    with (
        patch.object(svc, "open_blocking_connection", return_value=mock_conn),
        patch.object(svc, "declare_kb_index_topology"),
        patch.object(svc, "_drain_queue", return_value=list(msgs)),
        patch.object(svc, "_republish_queue") as repub,
    ):
        result = svc.mutate_queue_messages_by_job_ids(q, job_ids={14})

    assert result["removed"] == 1
    kept = repub.call_args.args[2]
    assert [body for _props, body in kept] == [
        b'{"job_id": 99}',
        b'{"file_id": 14}',
        b'not-json',
    ]


def test_mutate_delete_by_file_and_job_ids_requires_both_fields():
    q = "filex.gpu.mineru"
    msgs = [
        (None, b'{"job_id": 14, "file_id": 7}'),
        (None, b'{"job_id": 14, "file_id": 8}'),
        (None, b'{"job_id": 99, "file_id": 7}'),
        (None, b'{"job_id": 14}'),
    ]

    mock_ch = MagicMock()
    mock_conn = MagicMock()
    mock_conn.is_open = True
    mock_conn.channel.return_value = mock_ch

    with (
        patch.object(svc, "open_blocking_connection", return_value=mock_conn),
        patch.object(svc, "declare_kb_index_topology"),
        patch.object(svc, "_drain_queue", return_value=list(msgs)),
        patch.object(svc, "_republish_queue") as repub,
    ):
        result = svc.mutate_queue_messages_by_file_and_job_ids(
            q, file_id=7, job_ids={14}
        )

    assert result["removed"] == 1
    kept = repub.call_args.args[2]
    assert len(kept) == 3
    assert all(body != b'{"job_id": 14, "file_id": 7}' for _props, body in kept)


def test_mutate_purge():
    q = "kb.index.dlq"
    mock_ch = MagicMock()
    method = MagicMock()
    method.method.message_count = 3
    mock_ch.queue_purge.return_value = method
    mock_conn = MagicMock()
    mock_conn.is_open = True
    mock_conn.channel.return_value = mock_ch

    with (
        patch.object(svc, "open_blocking_connection", return_value=mock_conn),
        patch.object(svc, "declare_kb_index_topology"),
    ):
        result = svc.mutate_queue_messages(q, purge=True)

    assert result["removed"] == 3
    assert result["message_count"] == 0
    mock_ch.queue_purge.assert_called_once_with(queue=q)


def test_dedupe_queue_messages_keeps_first_per_job_id():
    q = "kb.extract"
    msgs = [
        (None, b'{"job_id": 47}'),
        (None, b'{"job_id": 47}'),
        (None, b'{"job_id": 46}'),
        (None, b'{"job_id": 47}'),
    ]

    def fake_drain(ch, queue_name, max_count=None):
        return list(msgs)

    mock_ch = MagicMock()
    mock_conn = MagicMock()
    mock_conn.is_open = True
    mock_conn.channel.return_value = mock_ch

    with (
        patch.object(svc, "open_blocking_connection", return_value=mock_conn),
        patch.object(svc, "_declare_admin_topologies"),
        patch.object(svc, "_drain_queue", side_effect=fake_drain),
        patch.object(svc, "_republish_queue") as repub,
        patch.object(svc, "_queue_message_count", return_value=2),
    ):
        result = svc.dedupe_queue_messages(q)

    assert result["removed"] == 2
    assert result["message_count"] == 2
    kept = repub.call_args[0][2]
    assert len(kept) == 2
    assert kept[0][1] == b'{"job_id": 47}'
    assert kept[1][1] == b'{"job_id": 46}'


def test_collapse_duplicate_job_items():
    items = [
        {"index": 0, "job_id": 47, "body_preview": "a"},
        {"index": 1, "job_id": 47, "body_preview": "b"},
        {"index": 2, "job_id": 46, "body_preview": "c"},
    ]
    collapsed, raw = svc._collapse_duplicate_job_items(items)
    assert raw == 3
    assert len(collapsed) == 2
    assert collapsed[0]["job_id"] == 47
    assert collapsed[0]["duplicate_count"] == 2
    assert collapsed[0]["index"] == 0
    assert collapsed[1]["job_id"] == 46
    assert collapsed[1]["duplicate_count"] == 1
