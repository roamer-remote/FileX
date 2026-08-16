# Copyright (c) 2026 徐泽宇
"""kb_pipeline_metrics window aligns with Beijing naive operation_logs.created_at."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

from models.operation_log import OperationLog
from services.kb_pipeline_log_service import ACTION_KB_EXTRACT_DONE, format_kb_pipeline_detail
from services.kb_pipeline_metrics_service import _count_actions, _window_start


def test_window_start_uses_beijing_naive():
    fixed = datetime(2026, 7, 2, 16, 45, 0)
    with patch("services.kb_pipeline_metrics_service.naive_db_now", return_value=fixed):
        start = _window_start("24h")
    assert start == datetime(2026, 7, 1, 16, 45, 0)


def test_count_actions_respects_beijing_window(db_session, regular_user):
    fixed = datetime(2026, 7, 2, 16, 0, 0)
    db_session.add(
        OperationLog(
            user_id=regular_user.id,
            action=ACTION_KB_EXTRACT_DONE,
            target_type="file",
            target_id=501,
            detail=format_kb_pipeline_detail(provider="legacy"),
            created_at=fixed - timedelta(hours=23),
        )
    )
    db_session.add(
        OperationLog(
            user_id=regular_user.id,
            action=ACTION_KB_EXTRACT_DONE,
            target_type="file",
            target_id=502,
            detail=format_kb_pipeline_detail(provider="legacy"),
            created_at=fixed - timedelta(hours=25),
        )
    )
    db_session.commit()

    with patch("services.kb_pipeline_metrics_service.naive_db_now", return_value=fixed):
        assert _count_actions(db_session, "24h", frozenset({ACTION_KB_EXTRACT_DONE})) == 1
