# Copyright (c) 2026 徐泽宇
"""KB extract skip path: terminal extract_status when MD already exists."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from services.kb_extract_service import JOB_DONE, JOB_QUEUED, STATUS_PENDING, STATUS_READY, enqueue_extract, run_extract_job
from services.md_paths import md_note_path


@pytest.fixture
def pdf_with_md(db_session, regular_user, tmp_path, monkeypatch):
    md_dir = tmp_path / ".md_notes"
    md_dir.mkdir()
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("services.md_paths.MD_DIR", str(md_dir))
    f = FileModel(
        filename="x.bin",
        original_name="paper.pdf",
        file_path="/tmp/unused.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        extract_status=STATUS_READY,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    note = Path(md_note_path(f.id))
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("# existing note\n", encoding="utf-8")
    f.md_file_path = str(note)
    db_session.commit()
    return f


def test_run_extract_job_skips_when_md_exists_sets_ready(db_session, pdf_with_md):
    job = KbExtractJob(user_id=pdf_with_md.user_id, file_id=pdf_with_md.id, status=JOB_QUEUED, attempts=0)
    db_session.add(job)
    pdf_with_md.extract_status = STATUS_PENDING
    db_session.commit()

    run_extract_job(db_session, job)
    db_session.commit()
    db_session.refresh(job)
    db_session.refresh(pdf_with_md)

    assert job.status == JOB_DONE
    assert job.attempts == 0
    assert pdf_with_md.extract_status == STATUS_READY


@patch("services.kb_extract_service._notify_file")
@patch("services.kb_index_service.publish_index_job")
@patch("services.extract.providers.registry.extract_with_provider")
def test_run_extract_job_reextract_with_provider_runs_despite_existing_md(
    mock_extract, _mock_publish, _mock_notify, db_session, pdf_with_md
):
    from services.extract.base import ExtractResult

    mock_extract.return_value = ExtractResult(text="# new\n", engine="docling")
    job = KbExtractJob(
        user_id=pdf_with_md.user_id,
        file_id=pdf_with_md.id,
        status=JOB_QUEUED,
        provider="docling",
        attempts=0,
    )
    db_session.add(job)
    pdf_with_md.extract_status = STATUS_PENDING
    db_session.commit()

    run_extract_job(db_session, job)
    db_session.commit()
    db_session.refresh(job)
    db_session.refresh(pdf_with_md)

    assert job.status == JOB_DONE
    assert job.attempts == 1
    assert pdf_with_md.extract_status == STATUS_READY
    assert pdf_with_md.extract_engine == "docling"
    mock_extract.assert_called_once()


def test_enqueue_reextract_then_skip_clears_pending(db_session, pdf_with_md):
    job_id = enqueue_extract(db_session, pdf_with_md.user_id, pdf_with_md.id, for_reextract=True)
    assert job_id is not None
    db_session.commit()
    db_session.refresh(pdf_with_md)
    assert pdf_with_md.extract_status == STATUS_PENDING

    job = db_session.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
    run_extract_job(db_session, job)
    db_session.commit()
    db_session.refresh(pdf_with_md)

    assert pdf_with_md.extract_status == STATUS_READY
