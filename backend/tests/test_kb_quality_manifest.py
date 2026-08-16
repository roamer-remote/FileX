# Copyright (c) 2026 徐泽宇
"""187 T-1: deterministic extraction manifest projection tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.kb_pipeline_log_service import (
    ACTION_KB_EXTRACT_DONE,
    ACTION_KB_EXTRACT_ERROR,
    ACTION_KB_EXTRACT_FALLBACK,
    ACTION_KB_EXTRACT_SKIP,
    ACTION_KB_EXTRACT_DEFER,
    format_kb_pipeline_detail,
)
from services.kb_quality_manifest_service import (
    ManifestReadError,
    build_extraction_manifest,
    build_extraction_manifest_from_logs,
)
from models.operation_log import OperationLog


def _log(action: str, detail: str) -> SimpleNamespace:
    return SimpleNamespace(action=action, detail=detail, id=1, target_type="file", target_id=42)


def _done_detail(job_id: int = 7, **extra: object) -> str:
    return format_kb_pipeline_detail(
        job_id=job_id,
        provider="mineru",
        engine="mineru-v4",
        provider_ms=120,
        persist_ms=30,
        side_effects_ms=5,
        **extra,
    )


def test_manifest_schema_and_done_timing_are_stable():
    manifest = build_extraction_manifest_from_logs(
        42,
        [_log(ACTION_KB_EXTRACT_DONE, _done_detail(7, ocr_used=True, pdf_class="scan"))],
        job_id=7,
    )

    assert manifest.schema_version == "187.1"
    assert manifest.file_id == 42
    assert manifest.job_id == 7
    assert manifest.status == "done"
    assert manifest.provider == "mineru"
    assert manifest.engine == "mineru-v4"
    assert manifest.duration_ms == 155
    assert manifest.ocr == {"ocr_used": "true", "pdf_class": "scan"}
    assert manifest.provider_version is None
    assert manifest.source_version is None
    assert "prompt" not in manifest.model_dump(mode="json")


def test_manifest_ocr_is_limited_to_181_182_keys():
    detail = _done_detail(7, ocr_engine="mineru", ocr_api_key="SECRET", ocr_prompt="PRIVATE")

    manifest = build_extraction_manifest_from_logs(42, [_log(ACTION_KB_EXTRACT_DONE, detail)], job_id=7)

    assert manifest.ocr == {"ocr_engine": "mineru"}


@pytest.mark.parametrize(
    ("action", "reason", "expected_status"),
    [
        (ACTION_KB_EXTRACT_ERROR, "provider_timeout", "error"),
        (ACTION_KB_EXTRACT_SKIP, "hash_unchanged", "skip"),
        (ACTION_KB_EXTRACT_DEFER, "active_job_on_file", "defer"),
    ],
)
def test_manifest_maps_non_done_terminal_reason(action: str, reason: str, expected_status: str):
    detail = format_kb_pipeline_detail(job_id=7, provider="mineru", reason=reason)
    manifest = build_extraction_manifest_from_logs(42, [_log(action, detail)], job_id=7)

    assert manifest.status == expected_status
    assert manifest.status_reason == reason
    assert manifest.engine is None
    assert manifest.duration_ms is None


def test_manifest_merges_fallback_reason_only_with_same_job():
    logs = [
        _log(ACTION_KB_EXTRACT_FALLBACK, format_kb_pipeline_detail(job_id=7, reason="images_detected")),
        _log(ACTION_KB_EXTRACT_DONE, _done_detail(7)),
        _log(ACTION_KB_EXTRACT_FALLBACK, format_kb_pipeline_detail(job_id=8, reason="other_job")),
    ]

    manifest = build_extraction_manifest_from_logs(42, logs, job_id=7)

    assert manifest.degradation_reason == "images_detected"
    assert manifest.engine == "mineru-v4"
    assert manifest.duration_ms == 155


def test_manifest_missing_terminal_returns_deterministic_error():
    with pytest.raises(ManifestReadError, match="terminal_log_missing"):
        build_extraction_manifest_from_logs(
            42,
            [_log(ACTION_KB_EXTRACT_FALLBACK, format_kb_pipeline_detail(job_id=7, reason="fallback"))],
            job_id=7,
        )


def test_manifest_missing_timing_is_null_not_guessed():
    detail = format_kb_pipeline_detail(job_id=7, provider="legacy", engine="markitdown")
    manifest = build_extraction_manifest_from_logs(42, [_log(ACTION_KB_EXTRACT_DONE, detail)], job_id=7)

    assert manifest.duration_ms is None


def test_manifest_rejects_truncated_required_fields():
    truncated = format_kb_pipeline_detail(job_id=7, reason="x" * 2100)

    with pytest.raises(ManifestReadError, match="terminal_log_truncated"):
        build_extraction_manifest_from_logs(42, [_log(ACTION_KB_EXTRACT_ERROR, truncated)], job_id=7)


def test_manifest_marks_truncated_optional_fields_without_leaking_content():
    detail = format_kb_pipeline_detail(
        job_id=7,
        provider="legacy",
        engine="markitdown",
        provider_ms=1,
        persist_ms=2,
        side_effects_ms=3,
        z_optional_metadata="/models/" + "x" * 2100,
    )
    manifest = build_extraction_manifest_from_logs(42, [_log(ACTION_KB_EXTRACT_DONE, detail)], job_id=7)

    assert manifest.manifest_truncated is True
    assert "/models/" not in manifest.model_dump_json()


def test_manifest_db_reader_filters_file_and_job_without_cross_job_merge(
    db_session,
    regular_user,
):
    db_session.add_all(
        [
            OperationLog(
                user_id=regular_user.id,
                action=ACTION_KB_EXTRACT_DONE,
                target_type="file",
                target_id=42,
                detail=_done_detail(7),
            ),
            OperationLog(
                user_id=regular_user.id,
                action=ACTION_KB_EXTRACT_FALLBACK,
                target_type="file",
                target_id=42,
                detail=format_kb_pipeline_detail(job_id=8, reason="other_job"),
            ),
        ]
    )
    db_session.flush()

    manifest = build_extraction_manifest(db_session, 42, 7)

    assert manifest.job_id == 7
    assert manifest.degradation_reason is None


def test_manifest_projection_rejects_rows_from_other_file():
    row = _log(ACTION_KB_EXTRACT_DONE, _done_detail(7))
    row.target_id = 999

    with pytest.raises(ManifestReadError, match="terminal_log_missing"):
        build_extraction_manifest_from_logs(42, [row], job_id=7)
