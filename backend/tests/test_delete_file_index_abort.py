# Copyright (c) 2026 徐泽宇
"""删除文件时与正在运行的索引任务协作终止。"""

import os
from unittest.mock import patch

import pytest

from config import UPLOAD_DIR
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_index_job import KbIndexJob
from models.kb_extract_job import KbExtractJob
from services.kb_index_service import (
    CANCELLED_FILE_DELETED_MSG,
    JOB_ERROR,
    JOB_RUNNING,
    KbIndexJobAborted,
    abort_kb_index_jobs_for_file_delete,
    run_index_job,
    touch_kb_index_job_heartbeat,
)
from services.kb_extract_service import (
    CANCELLED_FILE_DELETED_MSG as EXTRACT_CANCELLED_FILE_DELETED_MSG,
    JOB_ERROR as EXTRACT_JOB_ERROR,
    JOB_RUNNING as EXTRACT_JOB_RUNNING,
    abort_kb_extract_jobs_for_file_delete,
)


@pytest.fixture
def sample_file(db_session, regular_user):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, "test_delete_abort.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# Title\n\nParagraph about microscopy imaging.\n\nSecond paragraph here.")
    f = FileModel(
        filename="x.bin",
        original_name="paper.pdf",
        file_path="/tmp/unused.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=md_path,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_abort_kb_index_jobs_for_file_delete_marks_running(db_session, sample_file):
    job = KbIndexJob(
        user_id=sample_file.user_id,
        file_id=sample_file.id,
        status=JOB_RUNNING,
        attempts=1,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    cancelled = abort_kb_index_jobs_for_file_delete(db_session, sample_file.id)
    db_session.commit()
    db_session.refresh(job)

    assert cancelled == [job.id]
    assert job.status == JOB_ERROR
    assert job.last_error == CANCELLED_FILE_DELETED_MSG


def test_abort_kb_extract_jobs_for_file_delete_marks_active(db_session, sample_file):
    job = KbExtractJob(
        user_id=sample_file.user_id,
        file_id=sample_file.id,
        status=EXTRACT_JOB_RUNNING,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    cancelled = abort_kb_extract_jobs_for_file_delete(db_session, sample_file.id)
    db_session.commit()
    db_session.refresh(job)

    assert cancelled == [job.id]
    assert job.status == EXTRACT_JOB_ERROR
    assert job.last_error == EXTRACT_CANCELLED_FILE_DELETED_MSG


def test_touch_kb_index_job_heartbeat_aborts_when_job_cancelled(db_session, sample_file):
    job = KbIndexJob(
        user_id=sample_file.user_id,
        file_id=sample_file.id,
        status=JOB_ERROR,
        last_error=CANCELLED_FILE_DELETED_MSG,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    with pytest.raises(KbIndexJobAborted):
        touch_kb_index_job_heartbeat(job.id)


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_index_service.resolve_embedding_vectors")
@patch("services.kb_index_service.resolve_index_text")
def test_run_index_job_aborts_before_persist_when_job_cancelled(
    mock_resolve_text,
    mock_embed,
    _mock_notify,
    db_session,
    sample_file,
):
    from config import OLLAMA_EMBED_DIM

    mock_resolve_text.return_value = ("hello world " * 20, "md")

    job = KbIndexJob(
        user_id=sample_file.user_id,
        file_id=sample_file.id,
        status=JOB_RUNNING,
        attempts=1,
    )
    db_session.add(job)
    sample_file.index_status = "indexing"
    db_session.commit()
    db_session.refresh(job)

    def cancel_during_embed(_db, _inputs, heartbeat_cb=None):
        job.status = JOB_ERROR
        job.last_error = CANCELLED_FILE_DELETED_MSG
        db_session.flush()
        return [[0.01] * OLLAMA_EMBED_DIM] * 3

    mock_embed.side_effect = cancel_during_embed

    run_index_job(db_session, job)
    db_session.commit()

    assert mock_embed.called
    assert db_session.query(KbChunk).filter_by(file_id=sample_file.id).count() == 0
