# Copyright (c) 2026 徐泽宇
"""187 bounded retrieval trace and index compatibility adapters."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from schemas.kb_retrieval_trace import RetrievalTrace

MAX_TRACE_IDS = 100
MAX_TRACE_BYTES = 16 * 1024
TRACE_SCHEMA_VERSION = "187.1"

_ID_KEYS = (
    "wiki_graph_neighbor_ids",
    "doc_entity_neighbor_ids",
    "sag_neighbor_event_ids",
    "raptor_drilldown_ids",
)
_SUMMARY_KEYS = (
    "wiki_graph_expanded",
    "wiki_graph_added_hits",
    "tag_cooc_expanded",
    "tag_cooc_added_hits",
    "doc_entity_expanded",
    "doc_entity_added_hits",
    "sag_expanded",
    "sag_added_hits",
    "sag_mode_requested",
    "sag_mode_effective",
    "sag_mode_degraded",
    "raptor_expanded",
    "raptor_added_hits",
    "cache_hit",
)
_SENSITIVE_FIELD = re.compile(
    r"prompt|secret|api[_-]?key|password|token|body|content|excerpt|text", re.I
)
_SENSITIVE_VALUE = re.compile(
    r"(?:api[_-]?key|password|secret|token)\s*(?:[:=]|\b)", re.I
)


def _bounded_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _safe_reason(value: Any, limit: int) -> str | None:
    text = _bounded_text(value, limit)
    if not text:
        return None
    if _SENSITIVE_VALUE.search(text):
        return "redacted"
    return text


def _safe_query(value: Any) -> str:
    text = _bounded_text(value, 256)
    return "redacted" if _SENSITIVE_VALUE.search(text) else text


def _bounded_ids(values: Any) -> list[int]:
    out: list[int] = []
    for value in values or []:
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item not in out:
            out.append(item)
        if len(out) >= MAX_TRACE_IDS:
            break
    return out


def _safe_compatibility(values: dict[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (values or {}).items():
        if _SENSITIVE_FIELD.search(str(key)):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)] = _bounded_text(value, 128) if isinstance(value, str) else value
    return safe


def build_index_compatibility_metadata(
    *,
    runtime_provider: str | None,
    embedding_model: str | None,
    embedding_dimension: int | None,
    index_pipeline_fingerprint: str | None,
    embed_header_version: str | None,
    chunk_fingerprint: str | None,
    expected_dimension: int | None = None,
) -> dict[str, Any]:
    """Project only existing index metadata; never changes routing behavior."""

    reason = "unknown"
    status = "unknown"
    if embedding_dimension is not None and expected_dimension is not None:
        if int(embedding_dimension) != int(expected_dimension):
            status = "mismatch_diagnostic"
            reason = "embedding_dimension_mismatch"
        else:
            status = "compatible"
            reason = "match"
    return {
        "provider": _bounded_text(runtime_provider, 128) or None,
        "embedding_model": _bounded_text(embedding_model, 128) or None,
        "dimension": embedding_dimension,
        "index_version": _bounded_text(index_pipeline_fingerprint, 128) or None,
        "schema_fingerprint": _bounded_text(embed_header_version, 128) or None,
        "chunk_fingerprint": _bounded_text(chunk_fingerprint, 128) or None,
        "compatibility_status": status,
        "compatibility_reason": reason,
        "route_changed": False,
        "refused": False,
    }


def _trace_payload_bytes(trace: RetrievalTrace) -> int:
    return len(json.dumps(trace.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")).encode())


def build_retrieval_trace(
    *,
    trace_id: str,
    request_scope: str,
    user_id: int | None,
    workspace_id: int | None,
    query: str,
    meta: dict[str, Any] | None,
    final_items: list[dict[str, Any]],
    cache_hit: bool | None = None,
    compatibility: dict[str, Any] | None = None,
    agent_run_id: str | None = None,
    job_id: int | None = None,
) -> RetrievalTrace:
    """Create the single bounded trace envelope from visible post-ACL results."""

    source = meta or {}
    funnel = source.get("debug_funnel") or {}
    final_file_ids = _bounded_ids(item.get("file_id") for item in final_items)
    final_chunk_ids = _bounded_ids(item.get("chunk_id") for item in final_items)
    input_truncated = len(final_items) > MAX_TRACE_IDS
    expansion_ids: list[int] = []
    for key in _ID_KEYS:
        raw_values = list(source.get(key) or [])
        if len(raw_values) > MAX_TRACE_IDS:
            input_truncated = True
        for value in _bounded_ids(raw_values):
            if value not in expansion_ids:
                expansion_ids.append(value)
            if len(expansion_ids) >= MAX_TRACE_IDS:
                break

    counts = {
        key: int(funnel[key])
        for key in ("vector_candidates", "fts_candidates", "merged_unique", "after_acl_filter", "after_rerank", "after_mmr")
        if funnel.get(key) is not None
    }
    counts["final_results"] = len(final_items)
    summary = {
        key: (_bounded_text(source[key], 128) if isinstance(source[key], str) else source[key])
        for key in _SUMMARY_KEYS
        if key in source and isinstance(source[key], (str, int, bool, float))
    }
    timings_source = (source.get("search_trace") or {}).get("timings_ms") or {}
    timings_ms = {
        str(key): round(float(value), 3)
        for key, value in timings_source.items()
        if isinstance(value, (int, float)) and float(value) >= 0
    }
    trace = RetrievalTrace(
        trace_id=_bounded_text(trace_id, 64),
        request_scope=_bounded_text(request_scope, 64),
        user_id=user_id,
        workspace_id=workspace_id,
        agent_run_id=_bounded_text(agent_run_id, 64) or None,
        job_id=job_id,
        status="completed",
        finished_at=datetime.now(timezone.utc),
        query_normalized=_safe_query(query),
        counts=counts,
        final_file_ids=final_file_ids,
        final_chunk_ids=final_chunk_ids,
        expansion_ids=expansion_ids,
        expansion_summary=summary,
        timings_ms=timings_ms,
        cache_hit=cache_hit,
        fallback_mode=_safe_reason(source.get("fallback_mode"), 64),
        fallback_reason=_safe_reason(source.get("fallback_reason"), 128),
        compatibility=_safe_compatibility(compatibility),
        truncated=input_truncated,
    )
    if _trace_payload_bytes(trace) <= MAX_TRACE_BYTES:
        return trace

    trace.truncated = True
    trace.timings_ms = {}
    trace.expansion_summary = {}
    trace.compatibility = {}
    trace.query_normalized = ""
    trace.fallback_mode = None
    trace.fallback_reason = None
    trace.agent_run_id = None
    while _trace_payload_bytes(trace) > MAX_TRACE_BYTES:
        candidates = [
            ("expansion_ids", trace.expansion_ids),
            ("final_chunk_ids", trace.final_chunk_ids),
            ("final_file_ids", trace.final_file_ids),
        ]
        target = next((name for name, values in candidates if values), None)
        if target is None:
            break
        values = getattr(trace, target)
        setattr(trace, target, values[: max(1, len(values) // 2)])
    return trace
