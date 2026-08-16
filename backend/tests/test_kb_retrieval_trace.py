# Copyright (c) 2026 徐泽宇
"""187 T-2: bounded retrieval trace and compatibility metadata tests."""

from __future__ import annotations

import json

from services.kb_retrieval_trace_service import (
    MAX_TRACE_BYTES,
    MAX_TRACE_IDS,
    build_index_compatibility_metadata,
    build_retrieval_trace,
)


def test_trace_is_typed_versioned_and_contains_only_visible_final_ids():
    trace = build_retrieval_trace(
        trace_id="trace-1",
        request_scope="request-1",
        user_id=10,
        workspace_id=20,
        query="  annual report  ",
        meta={
            "debug_funnel": {
                "vector_candidates": 12,
                "fts_candidates": 8,
                "after_acl_filter": 3,
            },
            "rerank_applied": True,
            "sag_added_hits": 2,
            "sag_neighbor_event_ids": [99],
        },
        final_items=[
            {"file_id": 7, "chunk_id": 70},
            {"file_id": 8, "chunk_id": 80},
        ],
        cache_hit=False,
        compatibility={"compatibility_status": "compatible"},
    )

    payload = trace.model_dump(mode="json")
    assert payload["schema_version"] == "187.1"
    assert payload["trace_id"] == "trace-1"
    assert payload["request_scope"] == "request-1"
    assert payload["final_file_ids"] == [7, 8]
    assert payload["final_chunk_ids"] == [70, 80]
    assert payload["counts"]["vector_candidates"] == 12
    assert payload["counts"]["after_acl_filter"] == 3
    assert payload["expansion_ids"] == [99]
    assert payload["cache_hit"] is False
    assert payload["compatibility"]["compatibility_status"] == "compatible"
    assert "annual report" in payload["query_normalized"]
    assert 999 not in payload["final_file_ids"]


def test_trace_projection_does_not_change_final_result_order():
    final_items = [
        {"file_id": 8, "chunk_id": 80, "score": 0.9},
        {"file_id": 7, "chunk_id": 70, "score": 0.8},
    ]
    before = [dict(item) for item in final_items]
    build_retrieval_trace(
        trace_id="trace-order",
        request_scope="request-order",
        user_id=10,
        workspace_id=20,
        query="q",
        meta={},
        final_items=final_items,
    )
    assert final_items == before
    assert [item["file_id"] for item in final_items] == [8, 7]


def test_trace_redacts_sensitive_values_and_caps_ids_and_bytes():
    trace = build_retrieval_trace(
        trace_id="trace-2",
        request_scope="request-2",
        user_id=10,
        workspace_id=20,
        query="q\nwith prompt-like text",
        meta={
            "debug_funnel": {"vector_candidates": 1000},
            "search_trace": {
                "prompt": "do not keep this",
                "api_key": "secret",
                "excerpt": "private body",
            },
            "fallback_reason": "provider_api_key=secret",
            "sag_neighbor_event_ids": list(range(500)),
        },
        final_items=[{"file_id": i, "chunk_id": i + 1000} for i in range(500)],
        cache_hit=True,
    )

    encoded = json.dumps(trace.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")).encode()
    payload = trace.model_dump(mode="json")
    assert len(payload["final_file_ids"]) <= MAX_TRACE_IDS
    assert len(payload["final_chunk_ids"]) <= MAX_TRACE_IDS
    assert len(payload["expansion_ids"]) <= MAX_TRACE_IDS
    assert len(encoded) <= MAX_TRACE_BYTES
    assert payload["truncated"] is True
    encoded_text = encoded.decode()
    assert "do not keep this" not in encoded_text
    assert "secret" not in encoded_text
    assert "private body" not in encoded_text
    assert "provider_api_key=secret" not in encoded_text


def test_trace_hard_caps_large_timing_payload():
    trace = build_retrieval_trace(
        trace_id="trace-timings",
        request_scope="request-timings",
        user_id=1,
        workspace_id=2,
        query="q",
        meta={"search_trace": {"timings_ms": {f"stage-{i}": 1 for i in range(5000)}}},
        final_items=[],
    )
    encoded = json.dumps(trace.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")).encode()
    assert trace.truncated is True
    assert len(encoded) <= MAX_TRACE_BYTES


def test_trace_preserves_benign_fallback_reasons_but_redacts_credential_queries():
    trace = build_retrieval_trace(
        trace_id="trace-redaction-boundary",
        request_scope="request-redaction-boundary",
        user_id=1,
        workspace_id=2,
        query="api_key=do-not-store",
        meta={
            "fallback_mode": "known",
            "fallback_reason": "text_extraction_failed_content_too_large",
        },
        final_items=[],
    )

    payload = trace.model_dump(mode="json")
    assert payload["fallback_reason"] == "text_extraction_failed_content_too_large"
    assert payload["query_normalized"] == "redacted"
    assert "do-not-store" not in json.dumps(payload, ensure_ascii=False)


def test_compatibility_metadata_uses_existing_sources_and_diagnoses_mismatch():
    metadata = build_index_compatibility_metadata(
        runtime_provider="pgvector",
        embedding_model="bge-m3:latest",
        embedding_dimension=1024,
        index_pipeline_fingerprint="pipeline-v3",
        embed_header_version="header-v2",
        chunk_fingerprint=None,
        expected_dimension=768,
    )

    assert metadata["provider"] == "pgvector"
    assert metadata["embedding_model"] == "bge-m3:latest"
    assert metadata["dimension"] == 1024
    assert metadata["index_version"] == "pipeline-v3"
    assert metadata["schema_fingerprint"] == "header-v2"
    assert metadata["chunk_fingerprint"] is None
    assert metadata["compatibility_status"] == "mismatch_diagnostic"
    assert metadata["compatibility_reason"] == "embedding_dimension_mismatch"
    assert metadata["route_changed"] is False
    assert metadata["refused"] is False


def test_compatibility_metadata_without_comparison_evidence_is_unknown():
    metadata = build_index_compatibility_metadata(
        runtime_provider="pgvector",
        embedding_model="bge-m3:latest",
        embedding_dimension=None,
        index_pipeline_fingerprint="pipeline-v3",
        embed_header_version=None,
        chunk_fingerprint=None,
    )

    assert metadata["compatibility_status"] == "unknown"
    assert metadata["compatibility_reason"] == "unknown"
    assert metadata["route_changed"] is False
    assert metadata["refused"] is False
