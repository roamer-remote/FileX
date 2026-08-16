"""Bounded, deduplicated failure telemetry over existing operation logs."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.operation_log import OperationLog
from schemas.rag_quality_failure import (
    FailureReason,
    FailureStage,
    RagQualityFailureEvent,
)


_SENSITIVE = re.compile(r"(?:api[_-]?key|password|prompt|secret|token|stack(?:trace)?)", re.I)
_REASONS = frozenset(
    {
        "timeout",
        "oom",
        "provider_fallback",
        "malformed_output",
        "partial_index",
        "unknown_provider",
        "acl_filtered",
        "unknown",
    }
)


def failure_event_key(
    *,
    stage: str,
    reason: str,
    file_id: int,
    job_id: int,
    request_id: str | None,
    trace_id: str | None,
    schema_version: str = "187.1",
) -> str:
    raw = "|".join(
        [
            schema_version,
            stage,
            reason,
            str(file_id),
            str(job_id),
            request_id or "",
            trace_id or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _bounded_safe_text(value: Any, limit: int) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    if _SENSITIVE.search(text):
        return "redacted"
    return text[:limit]


def build_failure_event(
    *,
    stage: str,
    reason: str,
    file_id: int,
    job_id: int,
    request_id: str | None,
    trace_id: str | None,
    provider: str | None = None,
    model_version: str | None = None,
    occurred_at: datetime | None = None,
    retryable: bool = False,
    summary: str | None = None,
) -> RagQualityFailureEvent:
    normalized_reason: FailureReason = reason if reason in _REASONS else "unknown"  # type: ignore[assignment]
    normalized_stage = stage if stage in {"extraction", "retrieval", "rerank", "evidence", "answer", "index"} else None
    if normalized_stage is None:
        raise ValueError("unknown_failure_stage")
    normalized_provider = _bounded_safe_text(provider, 128)
    normalized_summary = _bounded_safe_text(summary, 240) or "unknown"
    return RagQualityFailureEvent(
        event_key=failure_event_key(
            stage=normalized_stage,
            reason=normalized_reason,
            file_id=file_id,
            job_id=job_id,
            request_id=request_id,
            trace_id=trace_id,
        ),
        stage=normalized_stage,
        reason=normalized_reason,
        provider=normalized_provider,
        file_id=file_id,
        job_id=job_id,
        request_id=_bounded_safe_text(request_id, 128),
        trace_id=trace_id,
        model_version=_bounded_safe_text(model_version, 128),
        occurred_at=occurred_at or datetime.now(timezone.utc),
        retryable=retryable,
        summary=normalized_summary,
    )


def project_failure_event(detail: str | dict[str, Any] | None) -> RagQualityFailureEvent | None:
    """Parse only a structured event; raw operation-log text is not telemetry."""

    try:
        payload = json.loads(detail) if isinstance(detail, str) else detail
        if not isinstance(payload, dict) or payload.get("schema_version") != "187.1":
            return None
        return RagQualityFailureEvent.model_validate(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _bounded_failure_detail(event: RagQualityFailureEvent, max_chars: int = 2000) -> str:
    """Serialize a parseable event within the operation-log detail contract."""

    payload = event.model_dump(mode="json")
    detail = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(detail) <= max_chars:
        return detail
    payload.update({"provider": None, "model_version": None, "summary": "truncated"})
    detail = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(detail) > max_chars:
        raise ValueError("rag_quality_failure_detail_too_large")
    return detail


def persist_failure_event(
    db: Session,
    user_id: int,
    event: RagQualityFailureEvent,
    *,
    commit: bool = False,
) -> tuple[RagQualityFailureEvent, bool]:
    """Write one structured event to operation_logs, deduplicated by event_key."""

    rows = (
        db.query(OperationLog.detail)
        .filter(
            OperationLog.event_key == event.event_key,
        )
        .all()
    )
    for (detail,) in rows:
        existing = project_failure_event(detail)
        if existing is not None and existing.event_key == event.event_key:
            return existing, False

    detail = _bounded_failure_detail(event)
    try:
        # The failure event has a unique event_key.  Isolate a race on that
        # key so a preceding, uncommitted pipeline log is not rolled back.
        with db.begin_nested():
            db.add(
                OperationLog(
                    user_id=user_id,
                    action="rag_quality_failure",
                    target_type="file",
                    target_id=event.file_id,
                    event_key=event.event_key,
                    detail=detail,
                )
            )
            db.flush()
        if commit:
            db.commit()
    except IntegrityError:
        existing = db.query(OperationLog.detail).filter(OperationLog.event_key == event.event_key).first()
        if existing is not None:
            projected = project_failure_event(existing[0])
            if projected is not None:
                return projected, False
        raise
    return event, True
