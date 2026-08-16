# Copyright (c) 2026 徐泽宇
"""097: kb index job heartbeat vs stale reconciler."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from models.file import File as FileModel
from models.kb_index_job import KbIndexJob
from services.kb_index_service import (
    JOB_RUNNING,
    STATUS_INDEXING,
    reconcile_stale_kb_index_jobs,
    touch_kb_index_job_heartbeat,
)
from utils.timezone import naive_db_now


@pytest.fixture
def bind_heartbeat_session(db_session, monkeypatch):
    """097 专项：pytest savepoint 内 db_session 对外不可见，须临时替换 SessionLocal。

    仅用于本文件 heartbeat 测试；勿在其他模块复用，避免污染全局 Session 工厂。
    """
    monkeypatch.setattr("database.SessionLocal", lambda: db_session)
    return db_session


def test_touch_heartbeat_updates_running_job_updated_at(
    db_session, regular_user, bind_heartbeat_session
):
    f = FileModel(
        filename="hb.bin",
        original_name="hb.pdf",
        file_path="/tmp/hb.bin",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status=STATUS_INDEXING,
    )
    db_session.add(f)
    db_session.flush()
    old_time = naive_db_now() - timedelta(hours=2)
    job = KbIndexJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        updated_at=old_time,
    )
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    touch_kb_index_job_heartbeat(job_id)

    row = db_session.query(KbIndexJob).filter(KbIndexJob.id == job_id).one()
    assert row.status == JOB_RUNNING
    assert row.updated_at > old_time


def test_heartbeat_keeps_job_from_stale_reconcile(
    db_session, regular_user, monkeypatch, bind_heartbeat_session
):
    monkeypatch.setattr("services.kb_index_service.KB_INDEX_RUNNING_STALE_SEC", 900)
    f = FileModel(
        filename="hb2.bin",
        original_name="hb2.pdf",
        file_path="/tmp/hb2.bin",
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
    job_id = job.id

    touch_kb_index_job_heartbeat(job_id)

    stats = reconcile_stale_kb_index_jobs(db_session)
    db_session.commit()
    row = db_session.query(KbIndexJob).filter(KbIndexJob.id == job_id).one()

    assert stats["running_closed_error"] == 0
    assert row.status == JOB_RUNNING


def test_touch_heartbeat_uses_independent_session(db_session, regular_user, bind_heartbeat_session):
    """同连接 Session 有未提交变更时，heartbeat flush+commit 仍刷新 updated_at。"""
    f = FileModel(
        filename="hb3.bin",
        original_name="hb3.pdf",
        file_path="/tmp/hb3.bin",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status=STATUS_INDEXING,
    )
    db_session.add(f)
    db_session.flush()
    old_time = naive_db_now() - timedelta(hours=1)
    job = KbIndexJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        updated_at=old_time,
    )
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    f.index_error = "uncommitted in main session"
    touch_kb_index_job_heartbeat(job_id)

    row = db_session.query(KbIndexJob).filter(KbIndexJob.id == job_id).one()
    assert row.updated_at > old_time
    assert row.status == JOB_RUNNING


def test_touch_heartbeat_swallows_errors(monkeypatch):
    mock_session = MagicMock()
    mock_session.query.side_effect = RuntimeError("db down")
    monkeypatch.setattr("database.SessionLocal", lambda: mock_session)
    touch_kb_index_job_heartbeat(999)
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()
