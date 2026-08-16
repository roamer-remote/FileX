# Copyright (c) 2026 徐泽宇
"""Build persistent GPU queue candidates and dispatch one route (T-4/T-5).

Dispatch ordering contract:

1. select one queued route deterministically (selector);
2. acquire a *fresh* GPU lease for this attempt (``require_fresh=True``), so a
   concurrent dispatch with the same owner cannot reuse or release this lease;
3. claim the outbox (``queued`` -> ``claimed``) inside the same transaction,
   publish RabbitMQ, then commit ``published`` + the fresh lease. If the
   process dies after publish but before commit, the transaction rolls back
   (route stays ``queued``, no lease) and the consumer treats an early message
   for a ``queued`` route as ``waiting``, requeues it bounded and re-reads the
   route before dropping (see ``gpu_scheduler_consumer``); the dispatch loop
   re-publishes.
4. if the broker rejects the publish, reopen the route to ``queued`` and
   release the lease so the next pass re-publishes.

Duplicate execution is prevented by the outbox state machine: consumers may
only execute a route whose state is ``published`` (``claim_gpu_execution``),
never a ``queued`` retry.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models.gpu_scheduler import GpuSchedulerOutbox
from models.kb_extract_job import KbExtractJob
from models.kb_post_job import KbPostJob
from services.gpu_scheduler_selector import (
    GpuQueueCandidate,
    GpuSelection,
    select_next_gpu_job,
)
from services.gpu_scheduler_persistence import (
    OUTBOX_PUBLISHED,
    OUTBOX_QUEUED,
    GpuSchedulerLease,
    acquire_gpu_lease,
    claim_gpu_route,
    release_gpu_lease_if_owned,
)
from services.kb_extract_service import JOB_QUEUED as EXTRACT_QUEUED, JOB_WAITING_GPU as EXTRACT_WAITING_GPU
from services.kb_post_service import JOB_QUEUED as POST_QUEUED, JOB_WAITING_GPU as POST_WAITING_GPU
from utils.timezone import naive_db_now


@dataclass(frozen=True)
class PersistentGpuCandidate(GpuQueueCandidate):
    outbox_id: int
    file_id: int | None


@dataclass(frozen=True)
class GpuDispatchResult:
    candidate: PersistentGpuCandidate
    selection: GpuSelection
    lease: GpuSchedulerLease
    route_published: bool


def list_waiting_gpu_jobs(
    db: Session,
    *,
    publishable_only: bool = False,
) -> list[PersistentGpuCandidate]:
    """Return only persisted jobs that have a matching durable GPU route."""
    route_states = ("queued",) if publishable_only else ("queued", "published")
    routes = {
        (route.job_kind, route.job_id): route
        for route in db.execute(
            select(GpuSchedulerOutbox).where(
                GpuSchedulerOutbox.state.in_(route_states),
                GpuSchedulerOutbox.job_kind.in_(("mineru", "raptor")),
            )
        ).scalars()
    }
    candidates: list[PersistentGpuCandidate] = []
    # provider 显式为 mineru，或未 pin（reextract 按运行时默认解析为 mineru）
    # 但 enqueue 时已按默认建立 mineru durable route 的 job，都是调度候选。
    # 以 route 存在为准：provider IS NULL 且无 mineru route 的 job 不会被选中。
    extract_jobs = db.query(KbExtractJob).filter(
        KbExtractJob.status.in_((EXTRACT_QUEUED, EXTRACT_WAITING_GPU)),
        or_(KbExtractJob.provider == "mineru", KbExtractJob.provider.is_(None)),
    ).all()
    for job in extract_jobs:
        route = routes.get(("mineru", str(job.id)))
        if route is not None:
            candidates.append(
                PersistentGpuCandidate(
                    job_id=str(job.id),
                    job_kind="mineru",
                    created_at=job.created_at,
                    outbox_id=int(route.id),
                    file_id=int(job.file_id),
                )
            )
    post_jobs = db.query(KbPostJob).filter(
        KbPostJob.status.in_((POST_QUEUED, POST_WAITING_GPU)),
    ).all()
    for job in post_jobs:
        route = routes.get(("raptor", str(job.id)))
        if route is not None:
            candidates.append(
                PersistentGpuCandidate(
                    job_id=str(job.id),
                    job_kind="raptor",
                    created_at=job.created_at,
                    outbox_id=int(route.id),
                    file_id=int(job.file_id),
                )
            )
    return candidates


def choose_next_waiting_gpu_job(
    db: Session,
    *,
    now: datetime,
    current_model_group: str | None = None,
    current_batch_size: int = 0,
    batch_started_at: datetime | None = None,
    publishable_only: bool = False,
) -> tuple[PersistentGpuCandidate, GpuSelection] | None:
    """Choose the next route.

    Defaults to the full waiting set: queued routes awaiting dispatch plus
    published routes awaiting execution. Pass ``publishable_only=True`` to
    restrict to queued routes that still need dispatch. This mirrors
    ``list_waiting_gpu_jobs`` so both call sites share one candidate semantic.
    """
    candidates = list_waiting_gpu_jobs(db, publishable_only=publishable_only)
    selection = select_next_gpu_job(
        candidates,
        now=now,
        current_model_group=current_model_group,
        current_batch_size=current_batch_size,
        batch_started_at=batch_started_at,
    )
    if selection is None:
        return None
    candidate = next(
        item
        for item in candidates
        if (item.job_kind, item.job_id) == (selection.candidate.job_kind, selection.candidate.job_id)
    )
    return candidate, selection


def dispatch_next_gpu_route(
    db: Session,
    *,
    owner_id: str,
    gpu_id: str,
    now: datetime,
    publish,
    publishers: dict[str, Callable[[dict], object]] | None = None,
    current_model_group: str | None = None,
    current_batch_size: int = 0,
    batch_started_at: datetime | None = None,
    ttl_seconds: int = 60,
) -> GpuDispatchResult | None:
    """Select one queued route, fence the GPU owner, then publish exactly once.

    Ordering is claim -> publish -> commit: if the process dies after the broker
    accepted the message but before the DB commit, the whole transaction rolls
    back (route stays ``queued``, no lease is created) and the dispatch loop
    re-publishes the route; the consumer treats an early message for a
    ``queued`` route as ``waiting`` and drops it after bounded requeues. This
    keeps the crash window recoverable, unlike commit-then-publish which could
    leave a ``published`` route with no message and a forever-active lease.
    """
    candidates = list_waiting_gpu_jobs(db, publishable_only=True)
    selection = select_next_gpu_job(
        candidates,
        now=now,
        current_model_group=current_model_group,
        current_batch_size=current_batch_size,
        batch_started_at=batch_started_at,
    )
    if selection is None:
        return None
    candidate = next(
        item
        for item in candidates
        if (item.job_kind, item.job_id) == (selection.candidate.job_kind, selection.candidate.job_id)
    )
    publish_callable = (publishers or {}).get(candidate.job_kind, publish)
    if publish_callable is None:
        raise ValueError(f"no publisher registered for job_kind={candidate.job_kind}")
    lease = acquire_gpu_lease(
        db,
        gpu_id=gpu_id,
        owner_id=owner_id,
        ttl_seconds=ttl_seconds,
        now=now,
        require_fresh=True,
    )
    if lease is None:
        return None
    lease.active_job_id = candidate.job_id
    route = claim_gpu_route(db, outbox_id=candidate.outbox_id)
    if route is None:
        release_gpu_lease_if_owned(db, gpu_id=gpu_id, owner_id=owner_id, now=now)
        db.commit()
        return None
    payload = dict(route.payload or {})
    payload["attempt"] = route.attempt
    payload["handover_epoch"] = route.handover_epoch
    route.payload = payload
    db.flush()
    try:
        publish_callable(payload)
    except Exception:
        # 发布失败：显式把 route 退回 queued 并释放 lease 后提交，下一 tick
        # 可立即重试。若进程在发布后、commit 前崩溃，未提交的事务同样回滚
        # 恢复 route queued（无 lease），consumer 对早到消息有界 requeue 丢弃。
        route.state = OUTBOX_QUEUED
        route.published_at = None
        release_gpu_lease_if_owned(db, gpu_id=gpu_id, owner_id=owner_id, now=now)
        db.commit()
        raise
    route.state = OUTBOX_PUBLISHED
    route.published_at = naive_db_now()
    # 164 §7.3：把当前模型组驻留批状态回写到 lease，供下一 tick 继续计算
    # 5 job / 600s 批边界。只有 continue_mineru_batch 延续当前批；其余选择
    # （mineru 新批、RAPTOR 切换、aging）都开始新的批计数。
    if selection.reason == "continue_mineru_batch":
        lease.model_group = "mineru"
        lease.batch_size = current_batch_size + 1
        if lease.batch_started_at is None:
            lease.batch_started_at = now
    else:
        lease.model_group = selection.candidate.job_kind
        lease.batch_size = 1
        lease.batch_started_at = now
    db.commit()
    return GpuDispatchResult(candidate, selection, lease, route_published=True)
