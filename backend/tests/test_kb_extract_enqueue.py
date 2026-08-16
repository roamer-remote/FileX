# Copyright (c) 2026 徐泽宇
"""KB extract enqueue deduplication and job creation.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

import pytest

from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from services.kb_extract_service import JOB_ERROR, JOB_QUEUED, STATUS_PENDING, enqueue_extract, publish_extract_job, run_extract_job


@pytest.fixture
def sample_file(db_session, regular_user):
    f = FileModel(
        filename="x.bin",
        original_name="paper.pdf",
        file_path="/tmp/unused.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_enqueue_extract_creates_job(db_session, sample_file):
    sample_file.original_name = "scan.pdf"
    sample_file.mime_type = "application/pdf"
    sample_file.has_md = False
    db_session.commit()

    with patch("messaging.kb_extract_publisher.publish_kb_extract_job"):
        job_id = enqueue_extract(db_session, sample_file.user_id, sample_file.id)
        db_session.commit()
        assert job_id is not None
        publish_extract_job(db_session, sample_file.user_id, sample_file.id, job_id)

    db_session.refresh(sample_file)
    assert sample_file.extract_status == STATUS_PENDING
    job = db_session.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
    assert job is not None
    assert job.status == JOB_QUEUED


def test_enqueue_skips_when_not_extractable(db_session, sample_file):
    sample_file.original_name = "readme.md"
    sample_file.mime_type = "text/markdown"
    db_session.commit()
    job_id = enqueue_extract(db_session, sample_file.user_id, sample_file.id)
    assert job_id is None


def test_run_extract_job_file_not_found_increments_attempts(db_session, sample_file, admin_user):
    job = KbExtractJob(
        user_id=admin_user.id,
        file_id=sample_file.id,
        status=JOB_QUEUED,
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    run_extract_job(db_session, job)
    db_session.commit()
    db_session.refresh(job)

    assert job.status == JOB_ERROR
    assert job.last_error == "file not found"
    assert job.attempts == 1
