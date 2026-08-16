import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from models.gpu_scheduler import GpuSchedulerLease, GpuSchedulerOutbox
from services.gpu_scheduler_persistence import (
    GpuLeaseError,
    ack_gpu_route,
    acquire_gpu_lease,
    assert_gpu_lease_owner,
    claim_gpu_route,
    claim_gpu_execution,
    enqueue_gpu_route,
    heartbeat_gpu_lease,
    heartbeat_gpu_lease_if_owned,
    publish_gpu_route,
    rollback_gpu_batch_on_defer,
    release_gpu_execution,
    reopen_gpu_route,
    record_release_ack,
    record_watchdog_empty_confirmation,
)


def test_lease_expiry_does_not_allow_takeover_without_release_or_watchdog(db_session):
    t0 = datetime(2026, 8, 1, 0, 0, 0)
    first = acquire_gpu_lease(db_session, gpu_id="0", owner_id="worker-a", now=t0)
    db_session.commit()
    first_token = first.fencing_token
    first_epoch = first.handover_epoch

    assert acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id="worker-b",
        now=t0 + timedelta(seconds=120),
    ) is None

    assert record_watchdog_empty_confirmation(db_session, first, now=t0 + timedelta(seconds=120)) is False
    assert record_watchdog_empty_confirmation(db_session, first, now=t0 + timedelta(seconds=125)) is True
    db_session.commit()
    takeover = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id="worker-b",
        now=t0 + timedelta(seconds=126),
    )
    assert takeover is not None
    assert takeover.owner_id == "worker-b"
    assert takeover.fencing_token != first_token
    assert takeover.handover_epoch == first_epoch + 1


def test_watchdog_confirmation_rejected_after_takeover(engine):
    """watchdog 确认必须以 FOR UPDATE 重读后的当前 fencing token 为准：另一个
    session 接管后，旧 owner 进程内的确认写入必须被拒绝。"""
    t0 = datetime(2026, 8, 1, 0, 0, 0)
    gpu_id = f"wd-race-{uuid.uuid4().hex[:8]}"
    sched = Session(engine)
    try:
        first = acquire_gpu_lease(sched, gpu_id=gpu_id, owner_id="worker-a", now=t0)
        sched.commit()
        first_token = first.fencing_token
        # 模拟调度循环恢复 pass：lease 已载入本 session 的 identity map。
        preloaded = sched.query(GpuSchedulerLease).filter_by(gpu_id=gpu_id).one()
        assert preloaded.fencing_token == first_token

        other = Session(engine)
        try:
            row = other.query(GpuSchedulerLease).filter_by(gpu_id=gpu_id).one()
            record_release_ack(
                other,
                row,
                owner_id="worker-a",
                fencing_token=first_token,
                now=t0,
            )
            other.commit()
            takeover = acquire_gpu_lease(
                other,
                gpu_id=gpu_id,
                owner_id="worker-b",
                now=t0 + timedelta(seconds=1),
            )
            other.commit()
            takeover_token = takeover.fencing_token
        finally:
            other.close()

        assert (
            record_watchdog_empty_confirmation(
                sched, preloaded, now=t0 + timedelta(seconds=6)
            )
            is False
        )
        sched.rollback()
        verify = Session(engine)
        try:
            row = verify.query(GpuSchedulerLease).filter_by(gpu_id=gpu_id).one()
            assert row.fencing_token == takeover_token
            assert row.watchdog_empty_confirmations == 0
            assert row.state == "active"
        finally:
            verify.close()
    finally:
        sched.close()
        # Close first so the FOR UPDATE row lock is released, then remove the
        # committed rows so they cannot pollute later tests (the shared
        # db_session fixture does not clean gpu_scheduler_leases).
        cleanup = Session(engine)
        try:
            cleanup.query(GpuSchedulerLease).filter_by(gpu_id=gpu_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_rollback_gpu_batch_on_defer_decrements_and_clears(db_session):
    """defer 轮次回退一格批计数；回退到 0 时清空模型组/批次起始时间。"""
    t0 = datetime(2026, 8, 1, 0, 0, 0)
    lease = acquire_gpu_lease(db_session, gpu_id="batch-defer", owner_id="worker-a", now=t0)
    lease.active_job_id = "42"
    lease.model_group = "mineru"
    lease.batch_size = 2
    lease.batch_started_at = t0
    db_session.commit()

    assert rollback_gpu_batch_on_defer(db_session, job_id="42", owner_id="worker-a")
    db_session.commit()
    db_session.expire_all()
    row = db_session.get(GpuSchedulerLease, lease.id)
    assert row.batch_size == 1
    assert row.model_group == "mineru"
    assert row.batch_started_at == t0

    assert rollback_gpu_batch_on_defer(db_session, job_id="42", owner_id="worker-a")
    db_session.commit()
    db_session.expire_all()
    row = db_session.get(GpuSchedulerLease, lease.id)
    assert row.batch_size == 0
    assert row.model_group is None
    assert row.batch_started_at is None

    # 已经为 0：不再回退（负计数保护），返回 False。
    assert not rollback_gpu_batch_on_defer(db_session, job_id="42", owner_id="worker-a")


def test_require_fresh_lease_is_never_renewed_for_same_owner(db_session):
    t0 = datetime(2026, 8, 1, 0, 0, 0)
    lease = acquire_gpu_lease(db_session, gpu_id="0", owner_id="worker-a", now=t0)
    db_session.commit()
    original_expiry = lease.lease_expires_at
    assert acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id="worker-a",
        now=t0 + timedelta(seconds=30),
        require_fresh=True,
    ) is None
    db_session.expire_all()
    lease = db_session.get(GpuSchedulerLease, lease.id)
    assert lease.owner_id == "worker-a"
    assert lease.lease_expires_at == original_expiry
    # Default behavior still renews for heartbeat-style acquisition.
    renewed = acquire_gpu_lease(
        db_session,
        gpu_id="0",
        owner_id="worker-a",
        now=t0 + timedelta(seconds=30),
    )
    assert renewed is not None
    assert renewed.lease_expires_at == t0 + timedelta(seconds=30 + 60)


def test_heartbeat_and_fencing_reject_stale_owner(db_session):
    lease = acquire_gpu_lease(db_session, gpu_id="0", owner_id="worker-a")
    db_session.commit()

    with pytest.raises(GpuLeaseError, match="mismatch"):
        heartbeat_gpu_lease(
            db_session,
            lease,
            owner_id="worker-b",
            fencing_token=lease.fencing_token,
        )
    assert_gpu_lease_owner(lease, owner_id="worker-a", fencing_token=lease.fencing_token)

    record_release_ack(
        db_session,
        lease,
        owner_id="worker-a",
        fencing_token=lease.fencing_token,
    )
    db_session.commit()
    with pytest.raises(GpuLeaseError, match="not active"):
        assert_gpu_lease_owner(lease, owner_id="worker-a", fencing_token=lease.fencing_token)


def test_heartbeat_if_owned_renews_current_owner(db_session):
    now = datetime(2026, 8, 1, 0, 0, 0)
    lease = acquire_gpu_lease(db_session, gpu_id="hb-renew-1", owner_id="worker-a", now=now)
    db_session.commit()

    later = now + timedelta(seconds=10)
    assert heartbeat_gpu_lease_if_owned(
        db_session,
        gpu_id="hb-renew-1",
        owner_id="worker-a",
        fencing_token=lease.fencing_token,
        ttl_seconds=30,
        now=later,
    ) is True
    db_session.expire_all()
    row = db_session.query(GpuSchedulerLease).filter_by(gpu_id="hb-renew-1").one()
    assert row.heartbeat_at == later
    assert row.lease_expires_at == later + timedelta(seconds=30)


def test_heartbeat_if_owned_rejects_stale_identity_map_after_takeover(engine):
    now = datetime(2026, 8, 1, 0, 0, 0)
    gpu_id = "hb-race-1"
    # A real committed session simulates the scheduler owner so the takeover
    # below can be seen by other connections.
    sched = Session(engine)
    try:
        first = acquire_gpu_lease(sched, gpu_id=gpu_id, owner_id="worker-a", now=now)
        sched.commit()
        first_token = first.fencing_token
        first_expiry = first.lease_expires_at

        # Reproduce the scheduler loop: owned leases are preloaded into the
        # session identity map before the heartbeat FOR UPDATE re-check runs.
        preloaded = (
            sched.query(GpuSchedulerLease)
            .filter(
                GpuSchedulerLease.owner_id == "worker-a",
                GpuSchedulerLease.state == "active",
            )
            .all()
        )
        assert [lease.gpu_id for lease in preloaded] == [gpu_id]

        # Another owner takes over between preload and heartbeat.
        other = Session(engine)
        try:
            row = other.query(GpuSchedulerLease).filter_by(gpu_id=gpu_id).one()
            row.owner_id = "worker-b"
            row.fencing_token = "token-b"
            row.handover_epoch = (row.handover_epoch or 0) + 1
            other.commit()
        finally:
            other.close()

        assert heartbeat_gpu_lease_if_owned(
            sched,
            gpu_id=gpu_id,
            owner_id="worker-a",
            fencing_token=first_token,
            ttl_seconds=30,
            now=now + timedelta(seconds=10),
        ) is False

        row = sched.get(GpuSchedulerLease, first.id)
        assert row.owner_id == "worker-b"
        assert row.fencing_token == "token-b"
        assert row.heartbeat_at == now
        assert row.lease_expires_at == first_expiry
    finally:
        # Close first so the FOR UPDATE row lock is released, then remove the
        # committed row so it cannot pollute later tests (the shared db_session
        # fixture does not clean gpu_scheduler_leases).
        sched.close()
        cleanup = Session(engine)
        try:
            cleanup.query(GpuSchedulerLease).filter_by(gpu_id=gpu_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_acquire_does_not_renew_stale_identity_map_after_takeover(engine):
    now = datetime(2026, 8, 1, 0, 0, 0)
    gpu_id = "hb-acquire-race-1"
    sched = Session(engine)
    try:
        first = acquire_gpu_lease(sched, gpu_id=gpu_id, owner_id="worker-a", now=now)
        sched.commit()
        first_expiry = first.lease_expires_at

        # A long-lived session reloads the lease into its identity map.
        assert sched.query(GpuSchedulerLease).filter_by(gpu_id=gpu_id).one().owner_id == "worker-a"

        other = Session(engine)
        try:
            row = other.query(GpuSchedulerLease).filter_by(gpu_id=gpu_id).one()
            row.owner_id = "worker-b"
            row.fencing_token = "token-b"
            row.handover_epoch = (row.handover_epoch or 0) + 1
            other.commit()
        finally:
            other.close()

        # require_fresh=False must not renew a lease already taken over.
        assert acquire_gpu_lease(
            sched,
            gpu_id=gpu_id,
            owner_id="worker-a",
            now=now + timedelta(seconds=30),
        ) is None
        row = sched.get(GpuSchedulerLease, first.id)
        assert row.owner_id == "worker-b"
        assert row.lease_expires_at == first_expiry
    finally:
        sched.close()
        cleanup = Session(engine)
        try:
            cleanup.query(GpuSchedulerLease).filter_by(gpu_id=gpu_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_outbox_idempotency_claim_and_ack_are_repeat_safe(db_session):
    first = enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=42,
        file_id=7,
        idempotency_key="mineru:42:1",
        payload={"job_id": 42, "job_kind": "mineru"},
        handover_epoch=3,
    )
    second = enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=42,
        file_id=7,
        idempotency_key="mineru:42:1",
        payload={"job_id": 42, "job_kind": "mineru"},
        handover_epoch=3,
    )
    assert first.id == second.id
    assert db_session.query(GpuSchedulerOutbox).count() == 1

    published = publish_gpu_route(
        db_session,
        outbox_id=first.id,
        publish=lambda payload: payload.update({"published": True}),
    )
    assert published.state == "published"
    assert published.attempt == 1
    assert claim_gpu_route(db_session, outbox_id=first.id) is None
    executing = claim_gpu_execution(db_session, job_kind="mineru", job_id=42)
    assert executing.state == "executing"
    assert claim_gpu_execution(db_session, job_kind="mineru", job_id=42) is None
    assert release_gpu_execution(db_session, outbox_id=first.id).state == "published"
    assert claim_gpu_execution(db_session, job_kind="mineru", job_id=42).state == "executing"

    retry = enqueue_gpu_route(
        db_session,
        job_kind="raptor",
        job_id=43,
        file_id=8,
        idempotency_key="raptor:43:0",
        payload={"job_id": 43},
    )
    with pytest.raises(RuntimeError, match="broker down"):
        publish_gpu_route(
            db_session,
            outbox_id=retry.id,
            publish=lambda _payload: (_ for _ in ()).throw(RuntimeError("broker down")),
        )
    assert db_session.get(GpuSchedulerOutbox, retry.id).state == "queued"
    assert publish_gpu_route(
        db_session,
        outbox_id=retry.id,
        publish=lambda _payload: None,
    ).state == "published"
    acked = ack_gpu_route(db_session, outbox_id=first.id)
    assert acked.state == "acked"
    acked = ack_gpu_route(db_session, outbox_id=retry.id)
    assert acked.state == "acked"
    assert ack_gpu_route(db_session, outbox_id=retry.id).state == "acked"


def test_reopen_gpu_route_starts_new_handover_generation(db_session):
    """每次 reopen 递增 outbox handover_epoch，使上一代已发布消息可被拒绝。"""
    first = enqueue_gpu_route(
        db_session,
        job_kind="mineru",
        job_id=42,
        file_id=7,
        idempotency_key="mineru:42:0",
        payload={"job_id": 42, "job_kind": "mineru"},
    )
    publish_gpu_route(db_session, outbox_id=first.id, publish=lambda _payload: None)
    reopened = reopen_gpu_route(db_session, outbox_id=first.id)
    assert reopened is not None
    assert reopened.state == "queued"
    assert reopened.handover_epoch == 1

    publish_gpu_route(db_session, outbox_id=first.id, publish=lambda _payload: None)
    reopened_again = reopen_gpu_route(db_session, outbox_id=first.id)
    assert reopened_again is not None
    assert reopened_again.handover_epoch == 2
