from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models.operation_log import OperationLog
from schemas.rag_quality_failure import RagQualityFailureEvent
from services.rag_quality_failure_service import (
    build_failure_event,
    failure_event_key,
    persist_failure_event,
    project_failure_event,
)


def test_failure_event_key_uses_pipe_delimited_contract_inputs() -> None:
    expected = hashlib.sha256(
        "|".join(["187.1", "retrieval", "timeout", "42", "7", "request-1", "trace-1"]).encode()
    ).hexdigest()[:32]
    assert failure_event_key(
        stage="retrieval",
        reason="timeout",
        file_id=42,
        job_id=7,
        request_id="request-1",
        trace_id="trace-1",
    ) == expected


def test_build_failure_event_maps_unknown_reason_and_redacts_summary() -> None:
    event = build_failure_event(
        stage="retrieval",
        reason="new_provider_exception",
        file_id=42,
        job_id=7,
        request_id="request-1",
        trace_id="a" * 32,
        summary="api_key=SECRET prompt=private stacktrace hidden",
    )

    assert event.reason == "unknown"
    assert event.summary == "redacted"
    assert len(event.event_key) == 32
    assert event.occurred_at.tzinfo is not None


def test_failure_event_rejects_extra_fields_and_invalid_taxonomy() -> None:
    with pytest.raises(ValidationError):
        RagQualityFailureEvent(
            event_key="a" * 32,
            stage="retrieval",
            reason="timeout",
            file_id=42,
            job_id=7,
            request_id="request-1",
            occurred_at=datetime.now(timezone.utc),
            retryable=True,
            summary="ok",
            secret="must-not-pass",
        )


def test_project_failure_event_reads_only_structured_operation_log_detail() -> None:
    event = build_failure_event(
        stage="index",
        reason="partial_index",
        file_id=42,
        job_id=7,
        request_id="request-1",
        trace_id=None,
        summary="partial index",
    )
    projected = project_failure_event(json.dumps(event.model_dump(mode="json")))
    assert projected == event
    assert project_failure_event("raw traceback and prompt=secret") is None


def test_persist_failure_event_deduplicates_by_event_key(db_session, regular_user) -> None:
    event = build_failure_event(
        stage="retrieval",
        reason="timeout",
        file_id=42,
        job_id=7,
        request_id="request-1",
        trace_id="a" * 32,
        summary="timeout",
    )

    first, created_first = persist_failure_event(db_session, regular_user.id, event)
    second, created_second = persist_failure_event(db_session, regular_user.id, event)

    assert first == event
    assert second == event
    assert created_first is True
    assert created_second is False


def test_persist_failure_event_detail_is_bounded_and_parseable(db_session, regular_user) -> None:
    event = build_failure_event(
        stage="retrieval",
        reason="timeout",
        file_id=42,
        job_id=7,
        request_id="request-1",
        trace_id="b" * 32,
        provider="p" * 128,
        model_version="m" * 128,
        summary="s" * 240,
    )
    persist_failure_event(db_session, regular_user.id, event)
    detail = db_session.query(OperationLog.detail).filter(OperationLog.event_key == event.event_key).one()[0]
    assert len(detail) <= 2000
    assert project_failure_event(detail) == event
