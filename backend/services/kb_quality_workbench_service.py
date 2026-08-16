# Copyright (c) 2026 徐泽宇
"""Pure projection helpers for the 187-P1 quality workbench."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

from schemas.kb_quality_workbench import (
    ProjectionState,
    QualityWorkbenchCorrelation,
    QualityWorkbenchResponse,
    BoundedFailureEvent,
)


TERMINAL_TRACE_STATUSES = frozenset(
    {"done", "completed", "success", "succeeded", "failed", "error", "cancelled", "skipped"}
)


def project_agent_quality_summary(
    summary: Mapping[str, Any] | None,
    *,
    file_id: int,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Project the existing agent coverage receipt without answer/evidence text."""

    if not isinstance(summary, Mapping):
        return None
    receipt = summary.get("coverage_receipt")
    if not isinstance(receipt, Mapping):
        return None
    selected = {int(value) for value in receipt.get("selected_file_ids", []) if str(value).isdigit()}
    covered = {int(value) for value in receipt.get("covered_file_ids", []) if str(value).isdigit()}
    if file_id not in selected:
        return None
    # This endpoint is a single-file projection; never carry other receipt IDs
    # across the current ACL boundary.
    selected = {file_id}
    covered = {file_id} if file_id in covered else set()
    dimensions: list[dict[str, Any]] = []
    for raw in receipt.get("dimensions", []):
        if not isinstance(raw, Mapping):
            continue
        dimension = {key: raw[key] for key in ("id", "type", "status", "reason_codes") if key in raw}
        if dimension:
            dimensions.append(dimension)
    answerable = receipt.get("answerable")
    evidence = {
        "version": receipt.get("version"),
        "answerable": answerable,
        "selected_file_ids": sorted(selected),
        "covered_file_ids": sorted(covered),
        "coverage": len(covered & selected) / len(selected) if selected else 0.0,
        "dimensions": dimensions,
    }
    answer = {
        "router_kind": summary.get("router_kind"),
        "answerable": answerable,
        "confidence": summary.get("confidence"),
        "missing_evidence": list(receipt.get("insufficient_reasons") or []),
    }
    return evidence, answer


def quality_workbench_query_hash(query: str) -> str:
    """Return the contract's bounded, content-free query correlation hash."""

    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


def _recency_key(trace: Mapping[str, Any]) -> tuple[int, Any, Any, int]:
    finished_at = trace.get("finished_at")
    created_at = trace.get("created_at")
    trace_id = trace.get("id") or 0
    return (
        1 if finished_at is not None else 0,
        finished_at or "",
        created_at or "",
        int(trace_id),
    )


def select_quality_trace(
    traces: Iterable[Mapping[str, Any]],
    *,
    file_id: int,
    job_id: int,
    trace_id: str | None = None,
) -> Mapping[str, Any] | None:
    """Select one trace without crossing the requested file/job boundary."""

    candidates = [
        trace
        for trace in traces
        if trace.get("file_id") == file_id
        and trace.get("job_id") == job_id
        and str(trace.get("status") or "").lower() in TERMINAL_TRACE_STATUSES
        and (trace_id is None or trace.get("trace_id") == trace_id)
    ]
    if not candidates:
        return None
    return max(candidates, key=_recency_key)


def build_bounded_quality_workbench_response(
    *,
    correlation: QualityWorkbenchCorrelation,
    extraction: ProjectionState,
    retrieval: ProjectionState,
    evidence: ProjectionState,
    answer: ProjectionState,
    failures: list[dict[str, Any]] | None = None,
    compatibility: dict[str, Any] | None = None,
    max_bytes: int = 64 * 1024,
) -> QualityWorkbenchResponse:
    """Build the response and apply the frozen final truncation order."""

    correlation = correlation.model_copy(update={
        "versions": {
            str(key)[:64]: (str(value)[:128] if value is not None else None)
            for key, value in list(correlation.versions.items())[:16]
        }
    })
    failure_items = [BoundedFailureEvent.model_validate(event) for event in (failures or [])]
    failure_items.sort(key=lambda event: (event.occurred_at, event.event_key), reverse=True)
    failure_count_truncated = len(failure_items) > 50
    response = QualityWorkbenchResponse(
        correlation=correlation,
        extraction=extraction,
        retrieval=retrieval,
        evidence=evidence,
        answer=answer,
        failures=failure_items[:50],
        compatibility=compatibility,
    )
    sections = ("retrieval", "evidence", "answer", "extraction", "failures")
    for section in sections:
        if len(response.model_dump_json().encode("utf-8")) <= max_bytes:
            break
        if section == "failures":
            response = response.model_copy(update={"failures": []})
        else:
            response = response.model_copy(
                update={section: ProjectionState(state="partial", data={"truncated": True})}
            )
        response = response.model_copy(
            update={
                "truncated": True,
                "truncated_sections": [*response.truncated_sections, section],
            }
        )
    if failure_count_truncated and "failures" not in response.truncated_sections:
        response = response.model_copy(
            update={
                "truncated": True,
                "truncated_sections": [*response.truncated_sections, "failures"],
            }
        )
    if len(response.model_dump_json().encode("utf-8")) > max_bytes:
        response = response.model_copy(update={"compatibility": None})
    if len(response.model_dump_json().encode("utf-8")) > max_bytes:
        # Compatibility is intentionally last.  If an unusually large
        # correlation/compatibility payload still exceeds the contract, return
        # a minimal valid 200 response rather than turning truncation into 500.
        response = QualityWorkbenchResponse(
            correlation=correlation.model_copy(update={"versions": {}}),
            extraction=ProjectionState(state="partial", data={"truncated": True}),
            retrieval=ProjectionState(state="partial", data={"truncated": True}),
            evidence=ProjectionState(state="partial", data={"truncated": True}),
            answer=ProjectionState(state="partial", data={"truncated": True}),
            failures=[],
            compatibility=None,
            truncated=True,
            truncated_sections=["retrieval", "evidence", "answer", "extraction", "failures", "compatibility"],
        )
    return response
