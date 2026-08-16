# Copyright (c) 2026 徐泽宇
"""127: KB worker lease fencing and running recovery."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from config import GPU_SCHEDULER_OWNER_ID, GPU_SCHEDULER_TTL_SEC
from models.file import File as FileModel
from models.gpu_scheduler import GpuSchedulerLease, GpuSchedulerOutbox
from models.kb_index_job import KbIndexJob
from models.kb_post_job import KbPostJob
from services.gpu_scheduler_persistence import (
    acquire_gpu_lease,
    claim_gpu_execution,
    enqueue_gpu_route,
    find_gpu_route,
    publish_gpu_route,
)
from services.kb_index_service import (
    JOB_QUEUED,
    JOB_RUNNING,
    STATUS_INDEXING,
    claim_kb_index_job,
    run_index_job,
    reconcile_stale_kb_index_jobs,
    touch_kb_index_job_heartbeat,
    KbIndexJobAborted,
)
from services.kb_post_service import (
    POST_STATUS_RUNNING,
    claim_kb_post_job,
    reconcile_stale_kb_post_jobs,
    run_post_job,
    touch_kb_post_job_heartbeat,
    KbPostJobAborted,
)
from services.system_setting_service import KEY_KB_POST_ASYNC_ENABLED, invalidate_settings_cache, update_settings
from utils.timezone import naive_db_now


def _file(db_session, regular_user, *, name: str = "lease.md", **fields) -> FileModel:
    f = FileModel(
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        **fields,
    )
    db_session.add(f)
    db_session.flush()
    return f


class _SessionProxy:
    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self) -> None:
        pass


def test_claim_kb_index_job_sets_worker_lease_and_rejects_second_claim(db_session, regular_user):
    f = _file(db_session, regular_user, index_status="pending")
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    db_session.add(job)
    db_session.commit()

    claimed = claim_kb_index_job(db_session, job.id, worker_id="index-worker-a")
    db_session.commit()
    assert claimed is not None
    assert claimed.status == JOB_RUNNING
    assert claimed.worker_id == "index-worker-a"
    assert claimed.lease_generation == 1
    assert claimed.claimed_at is not None
    assert claimed.heartbeat_at is not None

    assert claim_kb_index_job(db_session, job.id, worker_id="index-worker-b") is None


def test_index_heartbeat_requires_current_worker_lease(db_session, regular_user, monkeypatch):
    monkeypatch.setattr("database.SessionLocal", lambda: _SessionProxy(db_session))
    f = _file(db_session, regular_user, index_status=STATUS_INDEXING)
    old_time = naive_db_now() - timedelta(hours=1)
    job = KbIndexJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="owner",
        lease_generation=3,
        heartbeat_at=old_time,
    )
    db_session.add(job)
    db_session.commit()

    assert touch_kb_index_job_heartbeat(job.id, worker_id="other", lease_generation=3) is False
    db_session.refresh(job)
    assert job.heartbeat_at == old_time

    assert touch_kb_index_job_heartbeat(job.id, worker_id="owner", lease_generation=3) is True
    db_session.refresh(job)
    assert job.heartbeat_at > old_time


def test_reconcile_stale_index_running_requeues_and_bumps_generation(db_session, regular_user, monkeypatch):
    monkeypatch.setattr("services.kb_index_service.KB_INDEX_RUNNING_STALE_SEC", 900)
    f = _file(db_session, regular_user, index_status=STATUS_INDEXING)
    stale_time = naive_db_now() - timedelta(hours=2)
    job = KbIndexJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="dead-worker",
        lease_generation=4,
        heartbeat_at=stale_time,
        updated_at=stale_time,
    )
    db_session.add(job)
    db_session.commit()

    stats = reconcile_stale_kb_index_jobs(db_session)
    db_session.commit()
    db_session.refresh(job)
    db_session.refresh(f)

    assert stats["running_requeued"] == 1
    assert job.status == JOB_QUEUED
    assert job.worker_id is None
    assert job.lease_generation == 5
    assert f.index_status == "pending"


def test_claim_kb_post_job_sets_worker_lease(db_session, regular_user):
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()
    f = _file(db_session, regular_user, kb_post_status="queued")
    job = KbPostJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    db_session.add(job)
    db_session.commit()

    claimed = claim_kb_post_job(db_session, job.id, worker_id="post-worker-a")
    db_session.commit()

    assert claimed is not None
    assert claimed.status == JOB_RUNNING
    assert claimed.worker_id == "post-worker-a"
    assert claimed.lease_generation == 1
    assert claim_kb_post_job(db_session, job.id, worker_id="post-worker-b") is None


def test_post_heartbeat_requires_current_worker_lease(db_session, regular_user, monkeypatch):
    monkeypatch.setattr("database.SessionLocal", lambda: _SessionProxy(db_session))
    f = _file(db_session, regular_user, kb_post_status=POST_STATUS_RUNNING)
    old_time = naive_db_now() - timedelta(hours=1)
    job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="owner",
        lease_generation=2,
        heartbeat_at=old_time,
    )
    db_session.add(job)
    db_session.commit()

    assert touch_kb_post_job_heartbeat(job.id, worker_id="owner", lease_generation=1) is False
    db_session.refresh(job)
    assert job.heartbeat_at == old_time

    assert touch_kb_post_job_heartbeat(job.id, worker_id="owner", lease_generation=2) is True
    db_session.refresh(job)
    assert job.heartbeat_at > old_time


def test_reconcile_stale_post_fingerprint_mismatch_marks_error(db_session, regular_user, monkeypatch):
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()
    monkeypatch.setattr("services.kb_post_service.KB_POST_RUNNING_STALE_SEC", 900)
    f = _file(
        db_session,
        regular_user,
        kb_post_status=POST_STATUS_RUNNING,
        index_pipeline_fingerprint="current-fp",
    )
    stale_time = naive_db_now() - timedelta(hours=2)
    job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="dead-post-worker",
        lease_generation=7,
        heartbeat_at=stale_time,
        updated_at=stale_time,
        pipeline_fingerprint="old-fp",
    )
    db_session.add(job)
    db_session.commit()

    stats = reconcile_stale_kb_post_jobs(db_session)
    db_session.commit()
    db_session.refresh(job)
    db_session.refresh(f)

    assert stats["running_closed_error"] == 1
    assert stats["running_requeued"] == 0
    assert job.status == "error"
    assert "fingerprint" in (job.last_error or "")
    assert f.kb_post_status == "failed"


def test_reconcile_stale_post_matching_fingerprint_requeues(db_session, regular_user, monkeypatch):
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()
    monkeypatch.setattr("services.kb_post_service.KB_POST_RUNNING_STALE_SEC", 900)
    f = _file(
        db_session,
        regular_user,
        kb_post_status=POST_STATUS_RUNNING,
        index_pipeline_fingerprint="same-fp",
    )
    stale_time = naive_db_now() - timedelta(hours=2)
    job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="dead-post-worker",
        lease_generation=7,
        heartbeat_at=stale_time,
        updated_at=stale_time,
        pipeline_fingerprint="same-fp",
    )
    db_session.add(job)
    db_session.commit()

    stats = reconcile_stale_kb_post_jobs(db_session)
    db_session.commit()
    db_session.refresh(job)
    db_session.refresh(f)

    assert stats["running_requeued"] == 1
    assert job.status == JOB_QUEUED
    assert job.worker_id is None
    assert job.lease_generation == 8
    assert f.kb_post_status == "queued"


def test_reconcile_stale_post_requeue_recovers_executing_gpu_route(
    db_session, regular_user, monkeypatch
):
    """scheduler 崩溃后 GPU lease 心跳停止，但只有 watchdog 连续两次空确认后
    才允许重排队并恢复 route/lease；单次空确认只累计，不回收。"""
    import services.kb_post_service as post_service

    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()
    monkeypatch.setattr("services.kb_post_service.KB_POST_RUNNING_STALE_SEC", 900)
    f = _file(
        db_session,
        regular_user,
        kb_post_status=POST_STATUS_RUNNING,
        index_pipeline_fingerprint="same-fp",
    )
    now = datetime(2026, 8, 1, 0, 0, 0)
    stale_time = now - timedelta(hours=2)
    job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="dead-post-worker",
        lease_generation=7,
        heartbeat_at=stale_time,
        updated_at=stale_time,
        pipeline_fingerprint="same-fp",
    )
    db_session.add(job)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="raptor",
        job_id=job.id,
        file_id=f.id,
        idempotency_key=f"raptor:{job.id}:0",
        payload={"job_id": job.id, "job_kind": "raptor", "file_id": f.id},
    )
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    claim_gpu_execution(db_session, job_kind="raptor", job_id=job.id)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now - timedelta(seconds=2 * GPU_SCHEDULER_TTL_SEC + 1),
    )
    lease.active_job_id = str(job.id)
    db_session.commit()
    monkeypatch.setattr(post_service, "naive_db_now", lambda: now)
    monkeypatch.setattr(
        "services.gpu_watchdog.gpu_round_idle", lambda job_kind, lease: True
    )

    # 第一次空采样：只记录确认 #1，job 保持 running，route/lease 不动。
    stats = reconcile_stale_kb_post_jobs(db_session)
    db_session.commit()
    assert stats["running_requeued"] == 0
    db_session.expire_all()
    assert db_session.get(KbPostJob, job.id).status == JOB_RUNNING
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.watchdog_empty_confirmations == 1
    route = find_gpu_route(db_session, job_kind="raptor", job_id=job.id)
    assert route.state == "executing"

    # 第二次空采样（间隔 >= 5s）：确认 #2，允许重排队并恢复 route/lease。
    monkeypatch.setattr(
        post_service, "naive_db_now", lambda: now + timedelta(seconds=5)
    )
    stats = reconcile_stale_kb_post_jobs(db_session)
    db_session.commit()

    assert stats["running_requeued"] == 1
    db_session.refresh(job)
    assert job.status == JOB_QUEUED
    db_session.expire_all()
    route = find_gpu_route(db_session, job_kind="raptor", job_id=job.id)
    assert route.state == "queued"
    assert route.handover_epoch == 1
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_reconcile_stale_post_fingerprint_error_acks_executing_gpu_route(
    db_session, regular_user, monkeypatch
):
    """fingerprint mismatch 终态处理同样受 watchdog 门控：两次空确认后才
    ack route 并释放 dispatch lease，避免误收仍在执行的轮次。"""
    import services.kb_post_service as post_service

    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()
    monkeypatch.setattr("services.kb_post_service.KB_POST_RUNNING_STALE_SEC", 900)
    f = _file(
        db_session,
        regular_user,
        kb_post_status=POST_STATUS_RUNNING,
        index_pipeline_fingerprint="current-fp",
    )
    now = datetime(2026, 8, 1, 0, 0, 0)
    stale_time = now - timedelta(hours=2)
    job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="dead-post-worker",
        lease_generation=7,
        heartbeat_at=stale_time,
        updated_at=stale_time,
        pipeline_fingerprint="old-fp",
    )
    db_session.add(job)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="raptor",
        job_id=job.id,
        file_id=f.id,
        idempotency_key=f"raptor:{job.id}:0",
        payload={"job_id": job.id, "job_kind": "raptor", "file_id": f.id},
    )
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    claim_gpu_execution(db_session, job_kind="raptor", job_id=job.id)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now - timedelta(seconds=2 * GPU_SCHEDULER_TTL_SEC + 1),
    )
    lease.active_job_id = str(job.id)
    db_session.commit()
    monkeypatch.setattr(post_service, "naive_db_now", lambda: now)
    monkeypatch.setattr(
        "services.gpu_watchdog.gpu_round_idle", lambda job_kind, lease: True
    )

    # 第一次空采样：只累计确认，不 ack route / 不释放 lease。
    stats = reconcile_stale_kb_post_jobs(db_session)
    db_session.commit()
    assert stats["running_closed_error"] == 0
    db_session.expire_all()
    assert db_session.get(KbPostJob, job.id).status == JOB_RUNNING
    route = find_gpu_route(db_session, job_kind="raptor", job_id=job.id)
    assert route.state == "executing"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"

    # 第二次空采样（间隔 >= 5s）：确认 #2，置 error 并 ack/release。
    monkeypatch.setattr(
        post_service, "naive_db_now", lambda: now + timedelta(seconds=5)
    )
    stats = reconcile_stale_kb_post_jobs(db_session)
    db_session.commit()

    assert stats["running_closed_error"] == 1
    db_session.refresh(job)

    assert job.status == "error"
    db_session.expire_all()
    route = find_gpu_route(db_session, job_kind="raptor", job_id=job.id)
    assert route.state == "acked"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "released"
    assert lease.active_job_id is None


def test_reconcile_keeps_running_post_job_when_gpu_busy_despite_stale_lease(
    db_session, regular_user, monkeypatch
):
    """GPU 进程非空（或探测失败）时，post reconcile 不得 requeue 也不得释放
    lease：执行中的轮次必须保持 running，等待后续空采样（fail-closed）。"""
    import services.kb_post_service as post_service

    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()
    monkeypatch.setattr("services.kb_post_service.KB_POST_RUNNING_STALE_SEC", 900)
    f = _file(
        db_session,
        regular_user,
        kb_post_status=POST_STATUS_RUNNING,
        index_pipeline_fingerprint="same-fp",
    )
    now = datetime(2026, 8, 1, 0, 0, 0)
    stale_time = now - timedelta(hours=2)
    job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="dead-post-worker",
        lease_generation=7,
        heartbeat_at=stale_time,
        updated_at=stale_time,
        pipeline_fingerprint="same-fp",
    )
    db_session.add(job)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="raptor",
        job_id=job.id,
        file_id=f.id,
        idempotency_key=f"raptor:{job.id}:0",
        payload={"job_id": job.id, "job_kind": "raptor", "file_id": f.id},
    )
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    claim_gpu_execution(db_session, job_kind="raptor", job_id=job.id)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now - timedelta(seconds=2 * GPU_SCHEDULER_TTL_SEC + 1),
    )
    lease.active_job_id = str(job.id)
    db_session.commit()
    monkeypatch.setattr(post_service, "naive_db_now", lambda: now)
    monkeypatch.setattr(
        "services.gpu_watchdog.gpu_round_idle", lambda job_kind, lease: False
    )

    stats = reconcile_stale_kb_post_jobs(db_session)
    db_session.commit()
    assert stats["running_requeued"] == 0
    monkeypatch.setattr(
        post_service, "naive_db_now", lambda: now + timedelta(seconds=5)
    )
    stats = reconcile_stale_kb_post_jobs(db_session)
    db_session.commit()
    assert stats["running_requeued"] == 0
    db_session.expire_all()
    assert db_session.get(KbPostJob, job.id).status == JOB_RUNNING
    route = find_gpu_route(db_session, job_kind="raptor", job_id=job.id)
    assert route.state == "executing"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.watchdog_empty_confirmations == 0


def test_reconcile_skips_running_post_job_with_fresh_lease(
    db_session, regular_user, monkeypatch
):
    """GPU 模式下 lease 心跳是权威 liveness：job heartbeat 陈旧但 lease 心跳
    新鲜（执行轮仍存活，含 claim 后 running 提交前的瞬态）时不得 requeue。"""
    import services.kb_post_service as post_service

    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()
    monkeypatch.setattr("services.kb_post_service.KB_POST_RUNNING_STALE_SEC", 900)
    f = _file(
        db_session,
        regular_user,
        kb_post_status=POST_STATUS_RUNNING,
        index_pipeline_fingerprint="same-fp",
    )
    now = datetime(2026, 8, 1, 0, 0, 0)
    stale_time = now - timedelta(hours=2)
    job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="dead-post-worker",
        lease_generation=7,
        heartbeat_at=stale_time,
        updated_at=stale_time,
        pipeline_fingerprint="same-fp",
    )
    db_session.add(job)
    db_session.flush()
    route = enqueue_gpu_route(
        db_session,
        job_kind="raptor",
        job_id=job.id,
        file_id=f.id,
        idempotency_key=f"raptor:{job.id}:0",
        payload={"job_id": job.id, "job_kind": "raptor", "file_id": f.id},
    )
    publish_gpu_route(db_session, outbox_id=route.id, publish=lambda _payload: None)
    claim_gpu_execution(db_session, job_kind="raptor", job_id=job.id)
    lease = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id=GPU_SCHEDULER_OWNER_ID,
        now=now,
    )
    lease.active_job_id = str(job.id)
    db_session.commit()
    monkeypatch.setattr(post_service, "naive_db_now", lambda: now)

    stats = reconcile_stale_kb_post_jobs(db_session)
    db_session.commit()
    assert stats["running_requeued"] == 0
    db_session.expire_all()
    assert db_session.get(KbPostJob, job.id).status == JOB_RUNNING
    route = find_gpu_route(db_session, job_kind="raptor", job_id=job.id)
    assert route.state == "executing"
    lease = db_session.query(GpuSchedulerLease).filter_by(gpu_id="0").one()
    assert lease.state == "active"
    assert lease.watchdog_empty_confirmations == 0


def test_index_no_text_fast_terminal_checks_current_lease(db_session, regular_user, monkeypatch):
    f = _file(db_session, regular_user, has_md=True, index_status=STATUS_INDEXING)
    job = KbIndexJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="old-index-worker",
        lease_generation=1,
    )
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr("services.kb_index_service.resolve_index_text", lambda _f: ("", None))

    def _lost(*_args, **_kwargs):
        raise KbIndexJobAborted("lease lost")

    monkeypatch.setattr("services.kb_index_service._cooperative_index_abort_check", _lost)

    with pytest.raises(KbIndexJobAborted):
        run_index_job(db_session, job)

    db_session.refresh(job)
    db_session.refresh(f)
    assert job.status == JOB_RUNNING
    assert f.index_status == STATUS_INDEXING


def test_post_no_text_fast_terminal_checks_current_lease(db_session, regular_user, monkeypatch):
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()
    f = _file(db_session, regular_user, has_md=True, kb_post_status=POST_STATUS_RUNNING)
    job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="old-post-worker",
        lease_generation=1,
    )
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr("services.kb_post_service.resolve_index_text", lambda _f: ("", None))

    def _lost(*_args, **_kwargs):
        raise KbPostJobAborted("lease lost")

    monkeypatch.setattr("services.kb_post_service._cooperative_post_abort_check", _lost)

    with pytest.raises(KbPostJobAborted):
        run_post_job(db_session, job)

    db_session.refresh(job)
    db_session.refresh(f)
    assert job.status == JOB_RUNNING
    assert f.kb_post_status == POST_STATUS_RUNNING


# ── Critical #1: same-file concurrent claim ──────────────────────────────

def test_advisory_lock_serializes_same_file_claims(db_session, regular_user):
    """Claim serialization: advisory lock + same-file check prevents double claim.

    claim_kb_index_job uses pg_advisory_xact_lock(900127, file_id) so that two
    concurrent claims for the same file are serialized by the DB.  The first
    through marks its job RUNNING; the second then sees the RUNNING job and
    returns None.  This test verifies the second-claim rejection path.
    """
    f = _file(db_session, regular_user, index_status="pending")
    job_a = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    job_b = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    db_session.add_all([job_a, job_b])
    db_session.commit()

    # First claim succeeds
    claimed_a = claim_kb_index_job(db_session, job_a.id, worker_id="worker-1")
    db_session.commit()
    assert claimed_a is not None
    assert claimed_a.status == JOB_RUNNING

    # Second claim for same file sees the RUNNING job and returns None
    claimed_b = claim_kb_index_job(db_session, job_b.id, worker_id="worker-2")
    assert claimed_b is None


def test_post_claim_also_serializes_same_file(db_session, regular_user):
    """Same serialization for post claims: only one wins per file."""
    from services.system_setting_service import KEY_KB_POST_ASYNC_ENABLED, invalidate_settings_cache, update_settings
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "true"})
    invalidate_settings_cache()

    f = _file(db_session, regular_user, kb_post_status="queued")
    job_a = KbPostJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    job_b = KbPostJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    db_session.add_all([job_a, job_b])
    db_session.commit()

    claimed_a = claim_kb_post_job(db_session, job_a.id, worker_id="post-1")
    db_session.commit()
    assert claimed_a is not None
    assert claimed_a.status == JOB_RUNNING

    claimed_b = claim_kb_post_job(db_session, job_b.id, worker_id="post-2")
    assert claimed_b is None


def test_advisory_lock_key_isolation(db_session, regular_user):
    """Index (900127) and post (900128) advisory keys don't block each other."""
    from sqlalchemy import text

    f = _file(db_session, regular_user, index_status="pending", kb_post_status="queued")
    db_session.commit()

    # Acquire post lock in test tx, then claim index — must not block
    got_post = db_session.execute(
        text("SELECT pg_try_advisory_xact_lock(900128, :fid)"),
        {"fid": f.id},
    ).scalar()
    assert got_post is True

    job_i = KbIndexJob(user_id=regular_user.id, file_id=f.id, status=JOB_QUEUED)
    db_session.add(job_i)
    db_session.commit()

    claimed = claim_kb_index_job(db_session, job_i.id, worker_id="idx-w")
    assert claimed is not None  # Index claim works despite post lock held


def test_old_worker_token_cannot_recover_new_generation_index_job(db_session, regular_user, monkeypatch):
    """_recover_handler_error with old token must not touch a newer generation running job."""
    from messaging.kb_index_consumer import _recover_handler_error
    from services.kb_index_service import _LeaseToken

    monkeypatch.setattr("database.SessionLocal", lambda: _SessionProxy(db_session))

    f = _file(db_session, regular_user, index_status="pending")
    job = KbIndexJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="new-worker",
        lease_generation=5,
    )
    db_session.add(job)
    db_session.commit()

    old_token = _LeaseToken(worker_id="old-worker", lease_generation=3)
    _recover_handler_error(job.id, "old worker crashed", token=old_token)

    db_session.refresh(job)
    # Old token must NOT change the job owned by new-worker/gen=5
    assert job.status == JOB_RUNNING
    assert job.worker_id == "new-worker"
    assert job.lease_generation == 5
    assert (job.attempts or 0) == 0


def test_no_token_cannot_recover_running_index_job(db_session, regular_user, monkeypatch):
    """_recover_handler_error without a token must NOT touch any running job."""
    from messaging.kb_index_consumer import _recover_handler_error

    monkeypatch.setattr("database.SessionLocal", lambda: _SessionProxy(db_session))

    f = _file(db_session, regular_user, index_status="pending")
    job = KbIndexJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="some-worker",
        lease_generation=2,
    )
    db_session.add(job)
    db_session.commit()

    _recover_handler_error(job.id, "pre-dispatch error", token=None)

    db_session.refresh(job)
    assert job.status == JOB_RUNNING
    assert (job.attempts or 0) == 0


def test_old_worker_token_cannot_recover_new_generation_post_job(db_session, regular_user, monkeypatch):
    """_recover_handler_error with old token must not touch a newer generation post job."""
    from messaging.kb_post_consumer import _recover_handler_error
    from services.kb_post_service import _LeaseToken

    monkeypatch.setattr("database.SessionLocal", lambda: _SessionProxy(db_session))

    f = _file(db_session, regular_user, kb_post_status="running")
    job = KbPostJob(
        user_id=regular_user.id,
        file_id=f.id,
        status=JOB_RUNNING,
        worker_id="new-post-worker",
        lease_generation=4,
    )
    db_session.add(job)
    db_session.commit()

    old_token = _LeaseToken(worker_id="old-post-worker", lease_generation=1)
    _recover_handler_error(job.id, "old worker crashed", token=old_token)

    db_session.refresh(job)
    assert job.status == JOB_RUNNING
    assert job.worker_id == "new-post-worker"
    assert job.lease_generation == 4
    assert (job.attempts or 0) == 0
