# Copyright (c) 2026 徐泽宇
"""PostgreSQL-backed lease, fencing and GPU-route outbox primitives (T-3)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from datetime import datetime
from collections.abc import Callable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import GPU_SCHEDULER_OWNER_ID
from models.gpu_scheduler import GpuSchedulerLease, GpuSchedulerOutbox
from utils.timezone import naive_db_now

LEASE_ACTIVE = "active"
LEASE_RELEASED = "released"
OUTBOX_QUEUED = "queued"
OUTBOX_CLAIMED = "claimed"
OUTBOX_PUBLISHED = "published"
OUTBOX_EXECUTING = "executing"
OUTBOX_ACKED = "acked"
WATCHDOG_CONFIRM_INTERVAL_SEC = 5
WATCHDOG_CONFIRMATIONS_REQUIRED = 2


class GpuLeaseError(RuntimeError):
    """The lease owner or fencing token cannot perform the requested action."""


def _lease_for_update(db: Session, gpu_id: str) -> GpuSchedulerLease | None:
    return db.execute(
        select(GpuSchedulerLease)
        .where(GpuSchedulerLease.gpu_id == gpu_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def acquire_gpu_lease(
    db: Session,
    *,
    gpu_id: str,
    owner_id: str,
    ttl_seconds: int = 60,
    now: datetime | None = None,
    require_fresh: bool = False,
) -> GpuSchedulerLease | None:
    """Claim the single GPU only after release ack or two watchdog confirmations.

    Expiry is a liveness signal, never a permission to reclaim an executing lease.
    With ``require_fresh=True`` an already-active lease is never renewed, even for
    the same owner; callers use this for per-dispatch attempts that must not
    reuse (or later release) a lease held by a concurrent dispatch.
    """
    if not gpu_id.strip() or not owner_id.strip() or ttl_seconds <= 0:
        raise ValueError("gpu_id, owner_id and positive ttl_seconds are required")
    now = now or naive_db_now()
    lease = _lease_for_update(db, gpu_id)
    if lease is None:
        lease_values = {
            "gpu_id": gpu_id,
            "owner_id": owner_id,
            "fencing_token": str(uuid.uuid4()),
            "state": LEASE_ACTIVE,
            "lease_expires_at": now + timedelta(seconds=ttl_seconds),
            "heartbeat_at": now,
            "handover_epoch": 1,
        }
        inserted_id = db.execute(
            pg_insert(GpuSchedulerLease)
            .values(**lease_values)
            .on_conflict_do_nothing(index_elements=[GpuSchedulerLease.gpu_id])
            .returning(GpuSchedulerLease.id)
        ).scalar_one_or_none()
        if inserted_id is not None:
            return db.get(GpuSchedulerLease, inserted_id)
        # A concurrent owner won the unique gpu_id race; lock and evaluate
        # its fencing/release state without aborting the surrounding tx.
        lease = _lease_for_update(db, gpu_id)
        if lease is None:
            raise GpuLeaseError("gpu lease disappeared after concurrent insert")

    if lease.state == LEASE_ACTIVE:
        if lease.owner_id == owner_id:
            if require_fresh:
                return None
            lease.lease_expires_at = now + timedelta(seconds=ttl_seconds)
            lease.heartbeat_at = now
            db.flush()
            return lease
        if lease.release_ack_at is None and lease.watchdog_empty_confirmations < WATCHDOG_CONFIRMATIONS_REQUIRED:
            return None

    lease.owner_id = owner_id
    lease.fencing_token = str(uuid.uuid4())
    lease.state = LEASE_ACTIVE
    lease.lease_expires_at = now + timedelta(seconds=ttl_seconds)
    lease.heartbeat_at = now
    lease.active_job_id = None
    lease.release_ack_at = None
    lease.watchdog_empty_confirmations = 0
    lease.last_watchdog_at = None
    lease.handover_epoch = (lease.handover_epoch or 0) + 1
    db.flush()
    return lease


def heartbeat_gpu_lease(
    db: Session,
    lease: GpuSchedulerLease,
    *,
    owner_id: str,
    fencing_token: str,
    ttl_seconds: int = 60,
    now: datetime | None = None,
) -> None:
    assert_gpu_lease_owner(lease, owner_id=owner_id, fencing_token=fencing_token)
    now = now or naive_db_now()
    lease.heartbeat_at = now
    lease.lease_expires_at = now + timedelta(seconds=ttl_seconds)
    db.flush()


def heartbeat_gpu_lease_if_owned(
    db: Session,
    *,
    gpu_id: str,
    owner_id: str,
    fencing_token: str,
    ttl_seconds: int = 60,
    now: datetime | None = None,
) -> bool:
    """Heartbeat only when the current DB row is still active and owned.

    Unlike :func:`heartbeat_gpu_lease`, this re-checks the row under
    ``FOR UPDATE`` instead of trusting a possibly stale in-memory instance, so
    an owner taken over between query and heartbeat cannot keep writing.
    ``populate_existing`` forces the FOR UPDATE SELECT to refresh the row even
    when it is already loaded in this session's identity map.
    """
    now = now or naive_db_now()
    row = db.execute(
        select(GpuSchedulerLease)
        .where(GpuSchedulerLease.gpu_id == gpu_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None or row.state != LEASE_ACTIVE:
        return False
    if row.owner_id != owner_id or row.fencing_token != fencing_token:
        return False
    row.heartbeat_at = now
    row.lease_expires_at = now + timedelta(seconds=ttl_seconds)
    db.flush()
    return True


def record_release_ack(
    db: Session,
    lease: GpuSchedulerLease,
    *,
    owner_id: str,
    fencing_token: str,
    now: datetime | None = None,
) -> None:
    _assert_owner(lease, owner_id=owner_id, fencing_token=fencing_token)
    lease.state = LEASE_RELEASED
    lease.release_ack_at = now or naive_db_now()
    lease.active_job_id = None
    db.flush()


def record_watchdog_empty_confirmation(
    db: Session,
    lease: GpuSchedulerLease,
    *,
    now: datetime | None = None,
) -> bool:
    """Record one GPU-process-empty proof; return whether takeover is now allowed.

    The lease row is re-read under ``FOR UPDATE`` so two scheduler workers
    sampling the same GPU cannot interleave the confirmation counter, and a
    takeover that changed the fencing token between the caller's read and this
    write is never confirmed against the wrong owner.
    """
    now = now or naive_db_now()
    expected_token = lease.fencing_token
    row = _lease_for_update(db, lease.gpu_id)
    if row is None:
        return False
    if row.fencing_token != expected_token:
        # 已被其他 owner 接管：不得把空确认记到新 lease 上。
        return False
    if row.last_watchdog_at is not None:
        elapsed = (now - row.last_watchdog_at).total_seconds()
        if elapsed < WATCHDOG_CONFIRM_INTERVAL_SEC:
            return (row.watchdog_empty_confirmations or 0) >= WATCHDOG_CONFIRMATIONS_REQUIRED
    row.last_watchdog_at = now
    row.watchdog_empty_confirmations = min(
        WATCHDOG_CONFIRMATIONS_REQUIRED,
        (row.watchdog_empty_confirmations or 0) + 1,
    )
    if row.watchdog_empty_confirmations >= WATCHDOG_CONFIRMATIONS_REQUIRED:
        row.state = LEASE_RELEASED
        row.release_ack_at = now
        row.active_job_id = None
    db.flush()
    return row.watchdog_empty_confirmations >= WATCHDOG_CONFIRMATIONS_REQUIRED


def rollback_gpu_batch_on_defer(
    db: Session,
    *,
    job_id: int | str,
    owner_id: str = GPU_SCHEDULER_OWNER_ID,
    gpu_id: str | None = None,
    fencing_token: str | None = None,
) -> bool:
    """Roll back one dispatch-round batch increment after a deferred (no-op) round.

    ``dispatch_next_gpu_route`` increments ``lease.batch_size`` when it publishes
    a ``continue_mineru_batch`` route.  If the execution round ends
    ``waiting_gpu`` without running (model group busy / warming up), the route
    is reopened and the lease released; the increment must be rolled back,
    otherwise repeated deferrals inflate the counter toward the 5-job/600s
    boundary without any executed MinerU job (164 §7.3).  Returns whether the
    batch state was adjusted.
    """
    if gpu_id is not None:
        # 恢复路径：watchdog 二次确认已把 lease 置为 released 并清空
        # active_job_id，只能按 gpu_id + fencing token 定位原执行轮。
        row = _lease_for_update(db, gpu_id)
        if row is None:
            return False
        if fencing_token is not None and row.fencing_token != fencing_token:
            # 已被其他 owner 重新取得：不得回退新轮次的批计数。
            return False
        if row.active_job_id not in (None, str(job_id)):
            return False
    else:
        row = db.execute(
            select(GpuSchedulerLease)
            .where(
                GpuSchedulerLease.owner_id == owner_id,
                GpuSchedulerLease.active_job_id == str(job_id),
                GpuSchedulerLease.state == LEASE_ACTIVE,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if row is None:
            return False
    changed = False
    if (row.batch_size or 0) > 0:
        row.batch_size = (row.batch_size or 0) - 1
        changed = True
    if row.batch_size <= 0:
        if row.model_group is not None or row.batch_started_at is not None:
            row.model_group = None
            row.batch_started_at = None
            changed = True
    if not changed:
        return False
    db.flush()
    return True


def assert_gpu_lease_owner(
    lease: GpuSchedulerLease,
    *,
    owner_id: str,
    fencing_token: str,
) -> None:
    _assert_owner(lease, owner_id=owner_id, fencing_token=fencing_token)
    if lease.state != LEASE_ACTIVE:
        raise GpuLeaseError("gpu lease is not active")


def _assert_owner(lease: GpuSchedulerLease, *, owner_id: str, fencing_token: str) -> None:
    if lease.owner_id != owner_id or lease.fencing_token != fencing_token:
        raise GpuLeaseError("gpu lease owner or fencing token mismatch")


def enqueue_gpu_route(
    db: Session,
    *,
    job_kind: str,
    job_id: int | str,
    file_id: int | None,
    idempotency_key: str,
    payload: dict,
    handover_epoch: int = 0,
) -> GpuSchedulerOutbox:
    """Persist one route message; retries return the same record by idempotency key."""
    if not job_kind.strip() or not str(job_id).strip() or not idempotency_key.strip():
        raise ValueError("job_kind, job_id and idempotency_key are required")
    existing = db.execute(
        select(GpuSchedulerOutbox).where(GpuSchedulerOutbox.idempotency_key == idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    inserted_id = db.execute(
        pg_insert(GpuSchedulerOutbox)
        .values(
            job_kind=job_kind,
            job_id=str(job_id),
            file_id=file_id,
            idempotency_key=idempotency_key,
            payload=payload,
            handover_epoch=handover_epoch,
            state=OUTBOX_QUEUED,
        )
        .on_conflict_do_nothing(index_elements=[GpuSchedulerOutbox.idempotency_key])
        .returning(GpuSchedulerOutbox.id)
    ).scalar_one_or_none()
    if inserted_id is not None:
        return db.get(GpuSchedulerOutbox, inserted_id)
    return db.execute(
        select(GpuSchedulerOutbox).where(GpuSchedulerOutbox.idempotency_key == idempotency_key)
    ).scalar_one()


def find_gpu_route(
    db: Session,
    *,
    job_kind: str,
    job_id: int | str,
) -> GpuSchedulerOutbox | None:
    return db.execute(
        select(GpuSchedulerOutbox)
        .where(
            GpuSchedulerOutbox.job_kind == job_kind,
            GpuSchedulerOutbox.job_id == str(job_id),
        )
        .order_by(GpuSchedulerOutbox.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def claim_gpu_route(db: Session, *, outbox_id: int) -> GpuSchedulerOutbox | None:
    row = db.execute(
        select(GpuSchedulerOutbox)
        .where(GpuSchedulerOutbox.id == outbox_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None or row.state != OUTBOX_QUEUED:
        # A duplicate route message must not cause a second execution. The
        # caller can ack/inspect the existing row separately.
        return None
    row.state = OUTBOX_CLAIMED
    row.attempt = (row.attempt or 0) + 1
    row.published_at = naive_db_now()
    db.flush()
    return row


def claim_gpu_execution(
    db: Session,
    *,
    job_kind: str,
    job_id: int | str,
) -> GpuSchedulerOutbox | None:
    """Atomically reserve a published route for one executing consumer."""
    route = find_gpu_route(db, job_kind=job_kind, job_id=job_id)
    if route is None:
        return None
    row = db.execute(
        select(GpuSchedulerOutbox)
        .where(GpuSchedulerOutbox.id == route.id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None or row.state != OUTBOX_PUBLISHED:
        return None
    row.state = OUTBOX_EXECUTING
    db.flush()
    return row


def release_gpu_execution(db: Session, *, outbox_id: int) -> GpuSchedulerOutbox | None:
    row = db.execute(
        select(GpuSchedulerOutbox)
        .where(GpuSchedulerOutbox.id == outbox_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.state == OUTBOX_EXECUTING:
        row.state = OUTBOX_PUBLISHED
        db.flush()
    return row


def reopen_gpu_route(db: Session, *, outbox_id: int) -> GpuSchedulerOutbox | None:
    """Return a published route to ``queued`` for the next handover generation.

    Old consumers use this when GPU scheduling is enabled: a route that was
    published without a scheduler lease (legacy bridge) must go back to
    ``queued`` so the single dispatch owner re-publishes it under ``FOR
    UPDATE`` fencing. Executing routes are never reopened.

    Each reopen increments ``handover_epoch``: messages published before the
    reopen belong to the previous generation and are rejected as stale by the
    scheduler consumer, while dispatch re-publishes the route with the new
    epoch (164 §6 handover contract).
    """
    row = db.execute(
        select(GpuSchedulerOutbox)
        .where(GpuSchedulerOutbox.id == outbox_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None or row.state != OUTBOX_PUBLISHED:
        return None
    row.state = OUTBOX_QUEUED
    row.published_at = None
    row.handover_epoch = (row.handover_epoch or 0) + 1
    db.flush()
    return row


def release_gpu_lease_if_owned(
    db: Session,
    *,
    gpu_id: str,
    owner_id: str,
    now: datetime | None = None,
) -> bool:
    """Release the active lease for ``gpu_id`` only if this owner still holds it."""
    now = now or naive_db_now()
    row = db.execute(
        select(GpuSchedulerLease)
        .where(GpuSchedulerLease.gpu_id == gpu_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None or row.state != LEASE_ACTIVE or row.owner_id != owner_id:
        return False
    row.state = LEASE_RELEASED
    row.release_ack_at = now
    row.active_job_id = None
    db.flush()
    return True


def release_gpu_lease_for_job(
    db: Session,
    *,
    job_id: int | str,
    owner_id: str,
    now: datetime | None = None,
) -> bool:
    """Release the active lease pinned to ``active_job_id`` (post-execution ack)."""
    now = now or naive_db_now()
    row = db.execute(
        select(GpuSchedulerLease)
        .where(
            GpuSchedulerLease.owner_id == owner_id,
            GpuSchedulerLease.active_job_id == str(job_id),
            GpuSchedulerLease.state == LEASE_ACTIVE,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        return False
    row.state = LEASE_RELEASED
    row.release_ack_at = now
    row.active_job_id = None
    db.flush()
    return True


def find_active_lease_for_job(
    db: Session,
    *,
    job_id: int | str,
    owner_id: str | None = None,
) -> GpuSchedulerLease | None:
    """Return the active GPU lease pinned to ``job_id`` (if any).

    A running job is only live while its dispatch lease is still heartbeated;
    callers use this to distinguish an in-flight execution from an orphaned
    executing route after a scheduler crash/restart.
    """
    query = db.query(GpuSchedulerLease).filter(
        GpuSchedulerLease.active_job_id == str(job_id),
        GpuSchedulerLease.state == LEASE_ACTIVE,
    )
    if owner_id is not None:
        query = query.filter(GpuSchedulerLease.owner_id == owner_id)
    return query.first()


def publish_gpu_route(
    db: Session,
    *,
    outbox_id: int,
    publish: Callable[[dict], object],
) -> GpuSchedulerOutbox | None:
    """Publish one claimed payload and advance state only after the callback succeeds."""
    row = claim_gpu_route(db, outbox_id=outbox_id)
    if row is None:
        return None
    try:
        payload = dict(row.payload or {})
        payload["attempt"] = row.attempt
        payload["handover_epoch"] = row.handover_epoch
        publish(payload)
    except Exception:
        row.state = OUTBOX_QUEUED
        db.flush()
        raise
    row.payload = payload
    row.state = OUTBOX_PUBLISHED
    row.published_at = naive_db_now()
    db.flush()
    return row


def ack_gpu_route(db: Session, *, outbox_id: int) -> GpuSchedulerOutbox | None:
    row = db.get(GpuSchedulerOutbox, outbox_id)
    if row is None:
        return None
    if row.state == OUTBOX_ACKED:
        return row
    if row.state not in (OUTBOX_PUBLISHED, OUTBOX_EXECUTING):
        return None
    if row.state != OUTBOX_ACKED:
        row.state = OUTBOX_ACKED
        row.acked_at = naive_db_now()
        db.flush()
    return row


def ack_queued_gpu_route_for_terminal(
    db: Session,
    *,
    job_kind: str,
    job_id: int | str,
) -> bool:
    """Terminal job 的 queued route 直接 ack，避免 outbox 残留未派发行。

    dispatch 只选择 queued route + 非终态 job；job 终态后 queued route 不再被
    选中，这里显式收口到 acked（164 §6 幂等状态机，acked 视为已完成）。
    """
    route = find_gpu_route(db, job_kind=job_kind, job_id=job_id)
    if route is None or route.state != OUTBOX_QUEUED:
        return False
    route.state = OUTBOX_ACKED
    route.acked_at = naive_db_now()
    db.flush()
    return True


def recover_gpu_route_for_requeue(
    db: Session,
    *,
    job_kind: str,
    job_id: int | str,
    owner_id: str = GPU_SCHEDULER_OWNER_ID,
    rollback_batch: bool = False,
    gpu_id: str | None = None,
    fencing_token: str | None = None,
) -> bool:
    """executing route 需要重新发布时退回 queued 并释放 dispatch lease。

    job 被 stale reconcile 置回 queued，或执行轮以 waiting_gpu 结束 defer 后
    consumer 崩溃，route 都会停在 executing。退回 queued 并释放 lease 后，
    调度循环才能重新取得租约并发布（164 §6）。返回是否实际恢复。

    ``gpu_id``/``fencing_token`` 供 watchdog 已把 lease 置为 released 并清空
    ``active_job_id`` 的恢复路径使用：按 gpu 定位原执行轮并回退批计数，避免
    同一 job 在 5-job 批边界上重复计数（164 §7.3 以 job_id 计数）。
    """
    route = find_gpu_route(db, job_kind=job_kind, job_id=job_id)
    if route is None or route.state != OUTBOX_EXECUTING:
        return False
    release_gpu_execution(db, outbox_id=route.id)
    reopened = reopen_gpu_route(db, outbox_id=route.id)
    if rollback_batch:
        rollback_gpu_batch_on_defer(
            db,
            job_id=job_id,
            owner_id=owner_id,
            gpu_id=gpu_id,
            fencing_token=fencing_token,
        )
    release_gpu_lease_for_job(db, job_id=job_id, owner_id=owner_id)
    return reopened is not None


def ack_gpu_route_for_terminal(
    db: Session,
    *,
    job_kind: str,
    job_id: int | str,
    owner_id: str = GPU_SCHEDULER_OWNER_ID,
) -> bool:
    """executing route 对应 job 已进入终态时 ack route 并释放 dispatch lease。"""
    route = find_gpu_route(db, job_kind=job_kind, job_id=job_id)
    if route is None or route.state != OUTBOX_EXECUTING:
        return False
    ack_gpu_route(db, outbox_id=route.id)
    release_gpu_lease_for_job(db, job_id=job_id, owner_id=owner_id)
    return True
