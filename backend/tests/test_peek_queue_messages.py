# Copyright (c) 2026 徐泽宇
"""peek_queue_messages returns peek_count aligned with items length."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from services import rabbitmq_queue_admin_service as svc


def test_peek_queue_messages_peek_count_matches_items():
    q = "kb.extract"
    msgs = [(None, b'{"job_id": 329}'), (None, b'{"job_id": 330}')]

    def fake_drain(ch, queue_name, max_count=None):
        return list(msgs)

    counts = iter([2, 1])

    def fake_count(ch, queue_name):
        return next(counts)

    mock_ch = MagicMock()
    mock_conn = MagicMock()
    mock_conn.is_open = True
    mock_conn.channel.return_value = mock_ch

    with (
        patch.object(svc, "open_blocking_connection", return_value=mock_conn),
        patch.object(svc, "_declare_admin_topologies"),
        patch.object(svc, "_queue_message_count", side_effect=fake_count),
        patch.object(svc, "_drain_queue", side_effect=fake_drain),
        patch.object(svc, "_republish_queue"),
    ):
        result = svc.peek_queue_messages(q, limit=50)

    assert len(result["items"]) == 2
    assert result["peek_count"] == 2
    assert result["message_count"] == 1
    assert result["items"][0]["job_id"] == 329
    assert json.loads(result["items"][1]["raw_body"])["job_id"] == 330
