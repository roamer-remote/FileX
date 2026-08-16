# Copyright (c) 2026 徐泽宇
"""KB index enqueue + job processing (mocked Ollama / RabbitMQ).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import json
import logging
import os
from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_index_job import KbIndexJob
from services.kb_index_service import JOB_ERROR, JOB_QUEUED, enqueue_index, run_index_job


@pytest.fixture
def sample_file(db_session, regular_user):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, "test_note.md")
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


@patch("services.kb_index_service._notify_file_index")
@patch("messaging.kb_index_publisher.publish_kb_index_job")
@patch("services.kb_embed_cache_service.embed_texts")
def test_index_sidecar_md_becomes_ready(mock_embed, mock_publish, _mock_notify, db_session, sample_file):
    mock_embed.side_effect = lambda texts, **_kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]
    job_id = enqueue_index(db_session, sample_file.user_id, sample_file.id)
    db_session.commit()
    from services.kb_index_service import publish_index_job

    assert job_id is not None
    publish_index_job(db_session, sample_file.user_id, sample_file.id, job_id)
    job = db_session.query(KbIndexJob).filter(KbIndexJob.file_id == sample_file.id).one()
    assert job.status == JOB_QUEUED
    mock_publish.assert_called_once()
    run_index_job(db_session, job)
    db_session.commit()
    db_session.refresh(sample_file)
    assert sample_file.index_status == "ready"
    assert sample_file.chunk_count > 0
    chunks = db_session.query(KbChunk).filter(KbChunk.file_id == sample_file.id).all()
    assert len(chunks) == sample_file.chunk_count
    assert chunks[0].source == "sidecar_md"


@patch("services.kb_index_service._notify_file_index")
@patch("messaging.kb_index_publisher.publish_kb_index_job")
def test_enqueue_republish_when_job_already_queued(mock_publish, _mock_notify, db_session, sample_file):
    mock_publish.reset_mock()
    job_id = enqueue_index(db_session, sample_file.user_id, sample_file.id)
    db_session.commit()
    from services.kb_index_service import publish_index_job

    publish_index_job(db_session, sample_file.user_id, sample_file.id, job_id)
    mock_publish.assert_called_once()
    mock_publish.reset_mock()
    job_id2 = enqueue_index(db_session, sample_file.user_id, sample_file.id)
    db_session.commit()
    publish_index_job(db_session, sample_file.user_id, sample_file.id, job_id2)
    assert db_session.query(KbIndexJob).filter(KbIndexJob.file_id == sample_file.id).count() == 1
    mock_publish.assert_called_once()


@patch("messaging.kb_index_consumer.open_blocking_connection")
@patch("messaging.kb_index_publisher.publish_kb_index_job")
def test_replay_stale_only_skips_fresh_queued(mock_publish, _mock_conn, db_session, regular_user):
    from datetime import timedelta

    from messaging.kb_index_consumer import replay_queued_jobs
    from utils.timezone import naive_db_now

    f = FileModel(
        filename="stale.bin",
        original_name="stale.pdf",
        file_path="/tmp/stale",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    now = naive_db_now()
    fresh = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    fresh.updated_at = now
    stale = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    stale.updated_at = now - timedelta(minutes=10)
    db_session.add_all([fresh, stale])
    db_session.commit()

    n = replay_queued_jobs(db_session, full=False)
    assert n == 1
    mock_publish.assert_called_once()
    assert mock_publish.call_args.args[0] == stale.id


@patch("messaging.kb_index_consumer.open_blocking_connection")
@patch("messaging.kb_index_publisher.publish_kb_index_job")
def test_replay_full_publishes_all_queued(mock_publish, _mock_conn, db_session, regular_user):
    from messaging.kb_index_consumer import replay_queued_jobs
    from utils.timezone import naive_db_now

    f = FileModel(
        filename="full.bin",
        original_name="full.pdf",
        file_path="/tmp/full",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    job.updated_at = naive_db_now()
    db_session.add(job)
    db_session.commit()

    n = replay_queued_jobs(db_session, full=True)
    assert n == 1
    mock_publish.assert_called_once()

@patch("services.kb_index_service._notify_file_index")
@patch("messaging.kb_index_publisher.publish_kb_index_job")
@patch("services.kb_embed_cache_service.embed_texts")
def test_index_strips_nul_in_md(mock_embed, mock_publish, _mock_notify, db_session, sample_file, tmp_path):
    mock_embed.side_effect = lambda texts, **_kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]
    md = tmp_path / "note.md"
    md.write_text("title\x00body", encoding="utf-8")
    sample_file.has_md = True
    sample_file.md_file_path = str(md)
    db_session.commit()
    job_id = enqueue_index(db_session, sample_file.user_id, sample_file.id)
    db_session.commit()
    job = db_session.query(KbIndexJob).filter(KbIndexJob.id == job_id).first()
    run_index_job(db_session, job)
    db_session.commit()
    chunks = db_session.query(KbChunk).filter(KbChunk.file_id == sample_file.id).all()
    assert len(chunks) >= 1
    assert all("\x00" not in c.text for c in chunks)


def test_run_index_job_file_not_found_increments_attempts(db_session, sample_file, admin_user):
    job = KbIndexJob(
        user_id=admin_user.id,
        file_id=sample_file.id,
        status=JOB_QUEUED,
        attempts=0,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    run_index_job(db_session, job)
    db_session.commit()
    db_session.refresh(job)

    assert job.status == JOB_ERROR
    assert job.last_error == "file not found"
    assert job.attempts == 1

@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
def test_run_index_job_reuses_passed_effective(
    mock_embed, _mock_notify, db_session, sample_file, monkeypatch, regular_user
):
    from services.user_setting_service import get_user_effective_dict

    mock_embed.side_effect = lambda texts, **_kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]
    calls = {"n": 0}
    real = get_user_effective_dict

    def counted(db, uid):
        calls["n"] += 1
        return real(db, uid)

    monkeypatch.setattr("services.kb_index_service.get_user_effective_dict", counted)
    job_id = enqueue_index(db_session, sample_file.user_id, sample_file.id)
    db_session.commit()
    from services.kb_index_service import publish_index_job

    publish_index_job(db_session, sample_file.user_id, sample_file.id, job_id)
    job = db_session.query(KbIndexJob).filter(KbIndexJob.file_id == sample_file.id).one()
    effective = get_user_effective_dict(db_session, regular_user.id)
    calls["n"] = 0
    run_index_job(db_session, job, effective=effective)
    assert calls["n"] == 0

@patch("messaging.kb_index_consumer._handle_job")
@patch("messaging.kb_index_consumer.require_license_or_wait", return_value=True)
def test_on_message_logs_chinese_task_timing(
    _mock_license,
    mock_handle,
    db_session,
    sample_file,
    caplog,
):
    from messaging.kb_index_consumer import _on_message

    job = KbIndexJob(user_id=sample_file.user_id, file_id=sample_file.id, status=JOB_QUEUED)
    db_session.add(job)
    db_session.commit()

    class _Method:
        delivery_tag = 1

    class _Channel:
        connection = object()

        def basic_ack(self, delivery_tag: int) -> None:
            pass

    caplog.set_level(logging.INFO, logger="messaging.kb_index_consumer")
    _on_message(
        _Channel(),
        _Method(),
        None,
        json.dumps({"job_id": job.id}).encode("utf-8"),
    )
    mock_handle.assert_called_once()
    messages = [r.message for r in caplog.records if "索引消费者" in r.message]
    assert any("接到索引任务" in m and "开始时间=" in m for m in messages)
    assert any("索引任务结束" in m and "结束时间=" in m and "耗时=" in m for m in messages)

