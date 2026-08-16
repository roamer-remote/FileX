# Copyright (c) 2026 徐泽宇
"""081 Phase 1：extract 阶段耗时与 DONE 日志。"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from services.extract.base import ExtractResult
from services.kb_extract_service import JOB_QUEUED, run_extract_job
from services.kb_pipeline_log_service import ACTION_KB_EXTRACT_DONE


def _parse_detail_kv(detail: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in detail.split():
        if "=" in part:
            key, value = part.split("=", 1)
            out[key] = value
    return out


def _timing_fields(detail: str) -> dict[str, int]:
    kv = _parse_detail_kv(detail or "")
    return {key: int(kv[key]) for key in ("provider_ms", "persist_ms", "side_effects_ms") if key in kv}


@pytest.fixture
def pdf_file(db_session, regular_user):
    f = FileModel(
        filename="paper.pdf",
        original_name="paper.pdf",
        file_path="/tmp/paper.pdf",
        file_size=100,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


@pytest.fixture
def md_file(db_session, regular_user, tmp_path):
    src = tmp_path / "readme.md"
    src.write_text("# Title\n\nBody text", encoding="utf-8")
    f = FileModel(
        filename="readme",
        original_name="readme.md",
        file_path=str(src),
        file_size=src.stat().st_size,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


@patch("services.kb_extract_service._notify_file")
@patch("services.kb_index_service.publish_index_job")
@patch("services.extract.providers.registry.extract_with_provider")
def test_timing_fields_in_extract_done_log(
    mock_extract, _mock_publish, _mock_notify, db_session, regular_user, pdf_file
):
    from tests.test_kb_pipeline_operation_logs import _op_logs

    mock_extract.return_value = ExtractResult(text="# Title\n\nBody text.", engine="markitdown")
    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=pdf_file.id,
        status=JOB_QUEUED,
        provider="legacy",
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()

    run_extract_job(db_session, job)
    db_session.commit()

    done_row = next(
        row for row in _op_logs(db_session, regular_user.id, target_id=pdf_file.id) if row.action == ACTION_KB_EXTRACT_DONE
    )
    timings = _timing_fields(done_row.detail or "")
    assert set(timings) == {"provider_ms", "persist_ms", "side_effects_ms"}
    assert all(value >= 0 for value in timings.values())


@patch("services.kb_extract_service._notify_file")
@patch("services.kb_index_service.publish_index_job")
@patch("services.extract.providers.registry.extract_with_provider")
def test_timing_segments_are_exclusive(
    mock_extract, _mock_publish, _mock_notify, db_session, regular_user, pdf_file
):
    from tests.test_kb_pipeline_operation_logs import _op_logs

    mock_extract.return_value = ExtractResult(text="# Title\n\nBody text.", engine="markitdown")

    def slow_rebuild_anchors(db, user_id, file_id):
        time.sleep(0.05)
        return None

    job = KbExtractJob(
        user_id=regular_user.id,
        file_id=pdf_file.id,
        status=JOB_QUEUED,
        provider="legacy",
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()

    with patch("services.md_tag_anchor_service.rebuild_anchors_for_file", side_effect=slow_rebuild_anchors):
        run_extract_job(db_session, job)
        db_session.commit()

    done_row = next(
        row for row in _op_logs(db_session, regular_user.id, target_id=pdf_file.id) if row.action == ACTION_KB_EXTRACT_DONE
    )
    timings = _timing_fields(done_row.detail or "")
    assert timings["side_effects_ms"] >= 40
    assert timings["persist_ms"] < timings["side_effects_ms"]


@patch("services.kb_extract_service._notify_file")
@patch("services.kb_index_service.publish_index_job")
@patch("services.extract.providers.registry.extract_with_provider")
def test_done_log_persisted_for_registry(
    mock_extract, _mock_publish, _mock_notify, db_session, regular_user, pdf_file
):
    from tests.test_kb_pipeline_operation_logs import _op_logs

    mock_extract.return_value = ExtractResult(text="# Title\n\nBody.", engine="markitdown")
    job = KbExtractJob(user_id=regular_user.id, file_id=pdf_file.id, status=JOB_QUEUED, provider="legacy")
    db_session.add(job)
    db_session.commit()

    run_extract_job(db_session, job)
    db_session.commit()

    logs = _op_logs(db_session, regular_user.id, target_id=pdf_file.id)
    assert any(row.action == ACTION_KB_EXTRACT_DONE for row in logs)


@patch("services.kb_extract_service._notify_file")
@patch("services.kb_index_service.publish_index_job")
def test_done_log_persisted_for_markdown_copy(_mock_publish, _mock_notify, db_session, md_file):
    from tests.test_kb_pipeline_operation_logs import _op_logs

    job = KbExtractJob(user_id=md_file.user_id, file_id=md_file.id, status=JOB_QUEUED)
    db_session.add(job)
    db_session.commit()

    run_extract_job(db_session, job)
    db_session.commit()

    logs = _op_logs(db_session, md_file.user_id, target_id=md_file.id)
    done_rows = [row for row in logs if row.action == ACTION_KB_EXTRACT_DONE]
    assert len(done_rows) == 1
    assert _timing_fields(done_rows[0].detail or "")
