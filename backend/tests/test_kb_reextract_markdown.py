# Copyright (c) 2026 徐泽宇
"""Re-extract Markdown source files: copy to material note.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

import pytest

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from services.extract.policy import is_markdown_source_file, needs_extract, supports_reextract
from services.kb_extract_service import (
    JOB_DONE,
    JOB_QUEUED,
    STATUS_READY,
    copy_markdown_source_to_sidecar,
    enqueue_extract,
    run_extract_job,
)
from services.md_paths import md_note_path


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


def test_md_not_in_auto_extract(md_file):
    assert is_markdown_source_file(md_file) is True
    assert needs_extract(md_file) is False
    assert supports_reextract(md_file) is True


def test_copy_markdown_source_to_sidecar(md_file):
    text = copy_markdown_source_to_sidecar(md_file)
    assert "Body text" in text


def test_enqueue_reextract_md_creates_job(db_session, md_file):
    with patch("messaging.kb_extract_publisher.publish_kb_extract_job"):
        job_id = enqueue_extract(db_session, md_file.user_id, md_file.id, for_reextract=True)
    db_session.commit()
    assert job_id is not None
    job = db_session.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
    assert job is not None
    assert job.status == JOB_QUEUED


def test_run_extract_job_md_copy(db_session, md_file):
    job = KbExtractJob(user_id=md_file.user_id, file_id=md_file.id, status=JOB_QUEUED)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    with patch("services.kb_index_service.publish_index_job"):
        run_extract_job(db_session, job)

    db_session.refresh(md_file)
    db_session.refresh(job)
    assert job.status == JOB_DONE
    assert md_file.extract_status == STATUS_READY
    assert md_file.extract_engine == "markdown-copy"
    assert md_file.has_md is True
    sidecar = md_note_path(md_file.id)
    assert md_file.md_file_path == sidecar
    with open(sidecar, encoding="utf-8") as fh:
        assert "Body text" in fh.read()


def test_reextract_md_api(client, db_session, regular_user, jwt_token, md_file):
    with patch("services.kb_extract_service.publish_extract_job") as mock_pub:
        r = client.post(
            f"/api/knowledge-base/files/{md_file.id}/reextract",
            json={},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
    assert r.status_code == 200
    mock_pub.assert_called_once()
