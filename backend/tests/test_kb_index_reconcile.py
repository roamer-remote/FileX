# Copyright (c) 2026 徐泽宇
"""Tests for stale/superseded kb_index_jobs reconciliation.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from datetime import datetime, timedelta

from models.file import File as FileModel
from utils.timezone import naive_db_now
from models.kb_index_job import KbIndexJob
from services.kb_index_service import (
    JOB_DONE,
    JOB_RUNNING,
    STATUS_INDEXING,
    STATUS_READY,
    reconcile_stale_kb_index_jobs,
    reconcile_superseded_running_jobs,
)


def test_superseded_running_closed_when_newer_job_done(db_session, regular_user):
    f = FileModel(
        filename="a.bin",
        original_name="a.pdf",
        file_path="/tmp/a.bin",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status=STATUS_READY,
        chunk_count=3,
    )
    db_session.add(f)
    db_session.flush()
    zombie = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_RUNNING)
    done = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_DONE)
    db_session.add_all([zombie, done])
    db_session.commit()
    db_session.refresh(zombie)
    db_session.refresh(done)
    assert done.id > zombie.id

    n = reconcile_superseded_running_jobs(db_session, f.id, done.id)
    db_session.commit()
    db_session.refresh(zombie)

    assert n == 1
    assert zombie.status == JOB_DONE


def test_older_job_cleanup_does_not_close_newer_running_job(db_session, regular_user):
    f = FileModel(
        filename="race.bin",
        original_name="race.pdf",
        file_path="/tmp/race.bin",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status=STATUS_INDEXING,
        chunk_count=0,
    )
    db_session.add(f)
    db_session.flush()
    old_job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_RUNNING)
    new_job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_RUNNING)
    db_session.add_all([old_job, new_job])
    db_session.commit()
    db_session.refresh(old_job)
    db_session.refresh(new_job)
    assert new_job.id > old_job.id

    n = reconcile_superseded_running_jobs(db_session, f.id, old_job.id)
    db_session.commit()
    db_session.refresh(new_job)

    assert n == 0
    assert new_job.status == JOB_RUNNING


def test_stale_running_closed_when_file_already_ready(db_session, regular_user):
    f = FileModel(
        filename="b.bin",
        original_name="b.pdf",
        file_path="/tmp/b.bin",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status=STATUS_READY,
        chunk_count=1,
    )
    db_session.add(f)
    db_session.flush()
    job = KbIndexJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        updated_at=naive_db_now() - timedelta(hours=2),
    )
    db_session.add(job)
    db_session.commit()

    stats = reconcile_stale_kb_index_jobs(db_session)
    db_session.commit()
    db_session.refresh(job)

    assert stats["running_closed_done"] == 1
    assert job.status == JOB_DONE


def test_stale_running_by_time_requeues_when_still_indexing(db_session, regular_user):
    f = FileModel(
        filename="c.bin",
        original_name="c.pdf",
        file_path="/tmp/c.bin",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status=STATUS_INDEXING,
    )
    db_session.add(f)
    db_session.flush()
    job = KbIndexJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        updated_at=naive_db_now() - timedelta(hours=2),
    )
    db_session.add(job)
    db_session.commit()

    stats = reconcile_stale_kb_index_jobs(db_session)
    db_session.commit()
    db_session.refresh(job)
    db_session.refresh(f)

    assert stats["running_requeued"] == 1
    assert job.status == "queued"
    assert f.index_status == "pending"


def test_orphan_indexing_file_reset_to_pending(db_session, regular_user):
    f = FileModel(
        filename="d.bin",
        original_name="d.pdf",
        file_path="/tmp/d.bin",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status=STATUS_INDEXING,
    )
    db_session.add(f)
    db_session.commit()

    stats = reconcile_stale_kb_index_jobs(db_session)
    db_session.commit()
    db_session.refresh(f)

    assert stats["orphan_indexing_files"] == 1
    assert f.index_status == "pending"

def test_stale_running_by_time_beijing_naive_not_utc(db_session, regular_user, monkeypatch):
    """生产 Docker TZ=Asia/Shanghai：库内 updated_at 为北京时间 naive，须用同一时钟比较。"""
    from utils.timezone import BEIJING_TZ

    monkeypatch.setattr("services.kb_index_service.KB_INDEX_RUNNING_STALE_SEC", 900)
    fixed_beijing = datetime(2026, 5, 31, 18, 50, 0, tzinfo=BEIJING_TZ)
    monkeypatch.setattr("utils.timezone.beijing_now", lambda: fixed_beijing)

    f = FileModel(
        filename="e.bin",
        original_name="e.pdf",
        file_path="/tmp/e.bin",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status=STATUS_INDEXING,
    )
    db_session.add(f)
    db_session.flush()
    job = KbIndexJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        updated_at=datetime(2026, 5, 31, 18, 28, 34),
    )
    db_session.add(job)
    db_session.commit()

    stats = reconcile_stale_kb_index_jobs(db_session)
    db_session.commit()
    db_session.refresh(job)

    assert stats["running_requeued"] == 1
    assert job.status == "queued"
