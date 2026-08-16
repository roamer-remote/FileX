# Copyright (c) 2026 徐泽宇
"""121 KB index/post supersede commit and deadlock helpers."""

from __future__ import annotations

from sqlalchemy.exc import OperationalError

from models.file import File as FileModel
from models.kb_index_job import KbIndexJob
from models.kb_post_job import KbPostJob
from services.kb_index_service import JOB_DONE, JOB_QUEUED, enqueue_index, is_pg_deadlock
from services.kb_post_service import (
    JOB_ERROR,
    JOB_RUNNING,
    reconcile_and_commit_superseded_post_jobs,
    reconcile_superseded_running_post_jobs,
)


def test_is_pg_deadlock_detects_pgcode():
    class _Orig:
        pgcode = "40P01"

    assert is_pg_deadlock(OperationalError("stmt", {}, _Orig())) is True


def test_is_pg_deadlock_detects_message():
    assert is_pg_deadlock(OperationalError("deadlock detected", {}, None)) is True


def test_reconcile_helper_does_not_commit(db_session, regular_user, monkeypatch):
    f = FileModel(
        filename="a.pdf",
        original_name="a.pdf",
        file_path="/tmp/a.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        index_status="ready",
        chunk_count=1,
    )
    db_session.add(f)
    db_session.flush()
    db_session.add(
        KbPostJob(user_id=regular_user.id, file_id=f.id, status=JOB_RUNNING)
    )
    db_session.commit()

    commits: list[int] = []
    orig = db_session.commit

    def _track_commit():
        commits.append(1)
        return orig()

    monkeypatch.setattr(db_session, "commit", _track_commit)
    reconcile_superseded_running_post_jobs(db_session, f.id, superseding_index_job_id=999)
    assert commits == []


def test_reconcile_and_commit_invokes_commit(db_session, regular_user, monkeypatch):
    f = FileModel(
        filename="b.pdf",
        original_name="b.pdf",
        file_path="/tmp/b.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        index_status="indexing",
        chunk_count=0,
        raptor_built_chunk_count=8,
        raptor_built_md_chars=4000,
    )
    db_session.add(f)
    db_session.flush()
    post_job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
    )
    db_session.add(post_job)
    db_session.commit()

    commits: list[int] = []
    orig = db_session.commit

    def _track_commit():
        commits.append(1)
        return orig()

    monkeypatch.setattr(db_session, "commit", _track_commit)
    reconcile_and_commit_superseded_post_jobs(
        db_session, f.id, superseding_index_job_id=1001
    )
    assert len(commits) >= 1
    db_session.refresh(post_job)
    db_session.refresh(f)
    assert post_job.status == JOB_ERROR
    assert "superseded" in (post_job.last_error or "")
    assert f.raptor_built_chunk_count is None
    assert f.raptor_built_md_chars is None


def test_enqueue_index_commits_supersede_for_active_post(db_session, regular_user):
    f = FileModel(
        filename="c.pdf",
        original_name="c.pdf",
        file_path="/tmp/c.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        index_status="ready",
        chunk_count=2,
    )
    db_session.add(f)
    db_session.flush()
    post_job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
    )
    db_session.add(post_job)
    db_session.commit()

    job_id = enqueue_index(db_session, regular_user.id, f.id)
    assert job_id is not None
    db_session.commit()
    db_session.refresh(post_job)
    assert post_job.status == JOB_ERROR


def test_handle_job_deadlock_retry_succeeds(db_session, regular_user, monkeypatch):
    from messaging.kb_index_consumer import _handle_job

    f = FileModel(
        filename="d.pdf",
        original_name="d.pdf",
        file_path="/tmp/d.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        index_status="pending",
    )
    db_session.add(f)
    db_session.flush()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    db_session.add(job)
    db_session.commit()

    run_calls: list[bool] = []
    fail_next_loop_commit = [False]
    deadlock_commit_failed = [False]
    orig_commit = db_session.commit

    def fake_run_index_job(db, job_obj, *, effective=None, resume_after_deadlock=False):
        run_calls.append(resume_after_deadlock)
        job_obj.status = JOB_DONE
        fail_next_loop_commit[0] = True

    def flaky_commit():
        if fail_next_loop_commit[0] and not deadlock_commit_failed[0]:
            deadlock_commit_failed[0] = True
            fail_next_loop_commit[0] = False
            raise OperationalError("deadlock detected", {}, _DeadlockOrig())
        return orig_commit()

    class _DeadlockOrig:
        pgcode = "40P01"

    monkeypatch.setattr("messaging.kb_index_consumer.run_index_job", fake_run_index_job)
    monkeypatch.setattr("messaging.kb_index_consumer.reconcile_superseded_running_jobs", lambda *a, **k: False)
    monkeypatch.setattr(db_session, "commit", flaky_commit)
    monkeypatch.setattr(db_session, "rollback", db_session.expire_all)
    monkeypatch.setattr("messaging.kb_index_consumer.time.sleep", lambda _sec: None)

    _handle_job(db_session, job.id)

    assert run_calls == [False, True]
    db_session.refresh(job)
    assert job.status == JOB_DONE


def test_handle_job_deadlock_exhausted_calls_recover(db_session, regular_user, monkeypatch):
    from messaging.kb_index_consumer import _handle_job

    f = FileModel(
        filename="e.pdf",
        original_name="e.pdf",
        file_path="/tmp/e.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        index_status="pending",
    )
    db_session.add(f)
    db_session.flush()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    db_session.add(job)
    db_session.commit()

    recovered: list[tuple[int, str]] = []
    fail_next_loop_commit = [False]
    orig_commit = db_session.commit

    class _DeadlockOrig:
        pgcode = "40P01"

    def fake_run_index_job(db, job_obj, *, effective=None, resume_after_deadlock=False):
        fail_next_loop_commit[0] = True

    def always_deadlock_commit():
        if fail_next_loop_commit[0]:
            fail_next_loop_commit[0] = False
            raise OperationalError("deadlock detected", {}, _DeadlockOrig())
        return orig_commit()

    monkeypatch.setattr("messaging.kb_index_consumer.run_index_job", fake_run_index_job)
    monkeypatch.setattr("messaging.kb_index_consumer.reconcile_superseded_running_jobs", lambda *a, **k: False)
    monkeypatch.setattr(db_session, "commit", always_deadlock_commit)
    monkeypatch.setattr(db_session, "rollback", db_session.expire_all)
    monkeypatch.setattr("messaging.kb_index_consumer.time.sleep", lambda _sec: None)
    monkeypatch.setattr(
        "messaging.kb_index_consumer._recover_handler_error",
        lambda jid, detail, conn=None, token=None: recovered.append((jid, detail)),
    )

    _handle_job(db_session, job.id)

    assert len(recovered) == 1
    assert recovered[0][0] == job.id
    assert "deadlock detected" in recovered[0][1]
