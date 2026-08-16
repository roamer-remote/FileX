# Copyright (c) 2026 徐泽宇
"""067 T-1: kb_pipeline_log_service unit tests."""

from __future__ import annotations

from unittest.mock import patch

from models.operation_log import OperationLog
from services.kb_pipeline_log_service import (
    ACTION_KB_EXTRACT_DONE,
    ACTION_KB_EXTRACT_FALLBACK,
    ACTION_KB_EXTRACT_START,
    ALL_PIPELINE_ACTIONS,
    DETAIL_MAX_LEN,
    DETAIL_TRUNC_SUFFIX,
    format_kb_pipeline_detail,
    log_kb_pipeline_event,
)


def test_format_kb_pipeline_detail_sorts_keys_and_skips_none():
    assert format_kb_pipeline_detail(
        provider="mineru",
        job_id=42,
        engine=None,
        index_enqueued=True,
    ) == "index_enqueued=true job_id=42 provider=mineru"


def test_format_kb_pipeline_detail_truncates_long_text():
    long_reason = "x" * (DETAIL_MAX_LEN + 100)
    out = format_kb_pipeline_detail(job_id=1, reason=long_reason)
    assert len(out) == DETAIL_MAX_LEN
    assert out.endswith(DETAIL_TRUNC_SUFFIX)


def test_log_kb_pipeline_event_persists(db_session, regular_user):
    detail = format_kb_pipeline_detail(job_id=99, provider="legacy", engine="markitdown")
    log_kb_pipeline_event(
        db_session,
        regular_user.id,
        ACTION_KB_EXTRACT_START,
        file_id=7,
        detail=detail,
        commit=True,
    )
    row = (
        db_session.query(OperationLog)
        .filter(
            OperationLog.user_id == regular_user.id,
            OperationLog.action == ACTION_KB_EXTRACT_START,
            OperationLog.target_id == 7,
        )
        .order_by(OperationLog.id.desc())
        .first()
    )
    assert row is not None
    assert row.target_type == "file"
    assert row.detail == detail


def test_log_kb_pipeline_event_truncates_action(db_session, regular_user):
    long_action = "A" * 60
    log_kb_pipeline_event(
        db_session,
        regular_user.id,
        long_action,
        file_id=1,
        detail="job_id=1",
        commit=True,
    )
    row = (
        db_session.query(OperationLog)
        .filter(OperationLog.user_id == regular_user.id, OperationLog.target_id == 1)
        .order_by(OperationLog.id.desc())
        .first()
    )
    assert row is not None
    assert len(row.action) == 50


def test_log_kb_pipeline_event_swallows_log_operation_failure(db_session, regular_user):
    with patch("services.kb_pipeline_log_service.log_operation", side_effect=RuntimeError("db down")):
        log_kb_pipeline_event(
            db_session,
            regular_user.id,
            ACTION_KB_EXTRACT_DONE,
            file_id=1,
            detail="job_id=1",
        )


def test_action_constants_match_spec_appendix_a():
    assert ACTION_KB_EXTRACT_START == "KB 提取开始"
    assert ACTION_KB_EXTRACT_DONE == "KB 提取完成"
    assert ACTION_KB_EXTRACT_FALLBACK == "KB 提取失败回退"
    assert len(ALL_PIPELINE_ACTIONS) == 26
    for act in ALL_PIPELINE_ACTIONS:
        assert len(act) <= 50, f"{act!r} exceeds 50 chars"
        assert act == act.strip(), f"{act!r} has leading/trailing whitespace"
