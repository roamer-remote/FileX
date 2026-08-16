# Copyright (c) 2026 徐泽宇
"""048 md_content_hash extract skip + notify."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from services.kb_extract_service import (
    JOB_DONE,
    JOB_QUEUED,
    STATUS_READY,
    enqueue_extract,
    run_extract_job,
)
from services.md_hash_service import compute_md_content_hash, touch_md_content_hash
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
    content = "# existing note\n"
    note = Path(md_note_path(f.id))
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(content, encoding="utf-8")
    f.md_file_path = str(note)
    touch_md_content_hash(db_session, f, content=content)
    db_session.commit()
    return f


@patch("services.kb_extract_service._notify_file")
@patch("services.extract.providers.registry.extract_with_provider")
def test_run_extract_job_hash_skip_with_ready_status(mock_extract, mock_notify, db_session, pdf_with_md):
    job = KbExtractJob(user_id=pdf_with_md.user_id, file_id=pdf_with_md.id, status=JOB_QUEUED, attempts=0)
    db_session.add(job)
    assert pdf_with_md.extract_status == STATUS_READY
    db_session.commit()

    run_extract_job(db_session, job)
    db_session.commit()
    db_session.refresh(job)
    db_session.refresh(pdf_with_md)

    assert job.status == JOB_DONE
    assert job.last_error is None
    assert pdf_with_md.extract_status == STATUS_READY
    mock_notify.assert_called()
    mock_extract.assert_not_called()


@patch("services.kb_extract_service._notify_file")
def test_enqueue_reextract_with_provider_does_not_hash_skip(mock_notify, db_session, pdf_with_md):
    job_id = enqueue_extract(
        db_session,
        pdf_with_md.user_id,
        pdf_with_md.id,
        provider="docling",
        for_reextract=True,
    )
    assert job_id is not None
    job = db_session.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
    assert job is not None
    assert job.provider == "docling"
    mock_notify.assert_not_called()


@patch("services.kb_extract_service._notify_file")
def test_enqueue_reextract_skips_when_hash_unchanged(mock_notify, db_session, pdf_with_md):
    job_id = enqueue_extract(db_session, pdf_with_md.user_id, pdf_with_md.id, for_reextract=True)
    assert job_id is None
    assert pdf_with_md.extract_status == STATUS_READY
    mock_notify.assert_called_once()


@patch("messaging.kb_extract_publisher.publish_kb_extract_job")
def test_enqueue_force_does_not_hash_skip(_mock_publish, db_session, pdf_with_md):
    job_id = enqueue_extract(
        db_session,
        pdf_with_md.user_id,
        pdf_with_md.id,
        for_reextract=True,
        bypass_mineru_cache=True,
    )
    assert job_id is not None
    job = db_session.get(KbExtractJob, job_id)
    assert job is not None
    assert job.bypass_mineru_cache is True


def test_empty_okf_shell_does_not_hash_skip(db_session, regular_user, tmp_path, monkeypatch):
    """111：空 OKF 壳（待首次提取）不得因空 body hash 跳过 enqueue。"""
    from services.kb_extract_service import _md_extract_hash_unchanged
    from services.okf_note_service import create_okf_note_shell

    md_dir = tmp_path / ".md_notes"
    md_dir.mkdir()
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("services.md_paths.MD_DIR", str(md_dir))
    f = FileModel(
        filename="photo.png",
        original_name="photo.png",
        file_path=str(tmp_path / "photo.png"),
        file_size=100,
        mime_type="image/png",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    create_okf_note_shell(f)
    db_session.commit()

    assert _md_extract_hash_unchanged(f, bypass=False) is False


@patch("services.kb_extract_service._notify_file")
def test_enqueue_extract_empty_okf_shell_creates_job(mock_notify, db_session, regular_user, tmp_path, monkeypatch):
    from services.okf_note_service import create_okf_note_shell

    md_dir = tmp_path / ".md_notes"
    md_dir.mkdir()
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("services.md_paths.MD_DIR", str(md_dir))
    f = FileModel(
        filename="photo.png",
        original_name="photo.png",
        file_path=str(tmp_path / "photo.png"),
        file_size=100,
        mime_type="image/png",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    create_okf_note_shell(f)
    db_session.commit()

    job_id = enqueue_extract(db_session, regular_user.id, f.id)
    assert job_id is not None
    assert f.extract_status == "pending"
    mock_notify.assert_not_called()


def test_touch_md_content_hash_on_save(db_session, regular_user, tmp_path, monkeypatch):
    md_dir = tmp_path / ".md_notes"
    md_dir.mkdir()
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("services.md_paths.MD_DIR", str(md_dir))
    from services.md_note_service import save_md_note_for_file

    f = FileModel(
        filename="a.md",
        original_name="a.md",
        file_path="/tmp/a.md",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    with patch("services.md_note_service.rebuild_md_note_side_effects"):
        save_md_note_for_file(db_session, regular_user.id, f, "# hello\n", enqueue_vector_index=False)
    assert f.md_content_hash == compute_md_content_hash("# hello\n")
