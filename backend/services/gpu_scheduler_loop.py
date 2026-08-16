# Copyright (c) 2026 徐泽宇
"""Periodic GPU route dispatch loop (164 T-3/T-4).

The loop is the single dispatch owner: every tick it tries to publish one
queued route per configured ``gpu_id`` (through ``dispatch_next_gpu_route``,
which fences a fresh lease first) and heartbeats the leases this owner still
holds. Routes are published to the scheduler-owned ``filex.gpu.*`` queues; the
GPU scheduler consumer is the only executor of those routes (164 §6).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from config import (
    GPU_HIGH_RESIDENT_ENABLED,
    GPU_SCHEDULER_ENABLED,
    GPU_SCHEDULER_GPU_IDS,
    GPU_SCHEDULER_OWNER_ID,
    GPU_SCHEDULER_TICK_SEC,
    GPU_SCHEDULER_TTL_SEC,
)
from database import SessionLocal
from models.gpu_scheduler import GpuSchedulerLease
from services.gpu_high_mode import HIGH_DEGRADATION_WARMUP, HIGH_WARMUP_SAMPLE_SEC
from services.gpu_scheduler_dispatch import dispatch_next_gpu_route
from services.gpu_scheduler_persistence import heartbeat_gpu_lease_if_owned
from services.gpu_scheduler_selector import RAPTOR_MAX_WAIT_SEC
from services.gpu_watchdog import gpu_round_idle
from utils.timezone import naive_db_now

logger = logging.getLogger(__name__)


def _default_high_mode_sampler() -> dict[str, Any]:
    """默认 High 档采样：走系统资源探测（含 GPU 探针与显存公式）。"""
    from services.system_resource_service import collect_system_resources

    return collect_system_resources()


def _default_resident_mode_applier(enabled: bool) -> None:
    """默认 High 常驻应用：切换 scheduler runtime 的双模型组常驻开关。"""
    from services.gpu_scheduler_runtime import get_gpu_scheduler_runtime

    get_gpu_scheduler_runtime().set_resident_groups(enabled)


def _mineru_publisher(payload: dict) -> object:
    from messaging.gpu_queues import publish_gpu_route_message

    return publish_gpu_route_message("mineru", _normalize_route_payload(payload, "mineru"))


def _raptor_publisher(payload: dict) -> object:
    from messaging.gpu_queues import publish_gpu_route_message

    return publish_gpu_route_message("raptor", _normalize_route_payload(payload, "raptor"))


def _normalize_route_payload(payload: dict, job_kind: str) -> dict:
    """Backfill mandatory fields for legacy outbox rows (164 §6)."""
    normalized = dict(payload)
    job_id = str(normalized["job_id"])
    normalized.setdefault("job_kind", job_kind)
    normalized.setdefault("idempotency_key", f"{job_kind}:{job_id}:0")
    normalized.setdefault("attempt", 0)
    normalized.setdefault("handover_epoch", 0)
    return normalized


DEFAULT_GPU_PUBLISHERS: dict[str, Callable[[dict], object]] = {
    "mineru": _mineru_publisher,
    "raptor": _raptor_publisher,
}


def _lease_heartbeat_stale(
    lease: GpuSchedulerLease | None,
    *,
    now: datetime,
    stale_seconds: float,
) -> bool:
    """lease 缺失或心跳超过阈值视为 liveness 丢失。

    liveness 丢失只是进入 watchdog 确认的前提，本身不构成回收授权：
    ``_recover_stuck_executing_routes`` 仍需 release_ack 或两次 GPU 进程为空
    确认后才允许回收执行中的 lease（164 §5.5）。
    """
    if lease is None or lease.heartbeat_at is None:
        return True
    return (now - lease.heartbeat_at).total_seconds() > stale_seconds


@dataclass
class GpuSchedulerLoop:
    """One tick dispatches one route per gpu and heartbeats owned leases."""

    owner_id: str = GPU_SCHEDULER_OWNER_ID
    gpu_ids: list[str] = field(default_factory=lambda: list(GPU_SCHEDULER_GPU_IDS))
    tick_seconds: float = GPU_SCHEDULER_TICK_SEC
    ttl_seconds: int = GPU_SCHEDULER_TTL_SEC
    publishers: dict[str, Callable[[dict], object]] = field(
        default_factory=lambda: dict(DEFAULT_GPU_PUBLISHERS)
    )
    high_resident_enabled: bool = GPU_HIGH_RESIDENT_ENABLED
    high_mode_sampler: Callable[[], dict[str, Any]] | None = None
    resident_mode_applier: Callable[[bool], None] | None = None

    def __post_init__(self) -> None:
        if not self.owner_id.strip():
            raise ValueError("owner_id 不能为空")
        if not self.gpu_ids:
            raise ValueError("gpu_ids 不能为空")
        if self.tick_seconds <= 0:
            raise ValueError("tick_seconds 必须为正数")
        if self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须为正数")
        if not all(callable(self.publishers.get(kind)) for kind in ("mineru", "raptor")):
            raise ValueError("publishers 必须提供 mineru 与 raptor 两个 publisher")
        # 本进程实际持有的 fencing token（gpu_id -> token）。重启后的新进程
        # 不会续期上一进程留下的 lease，否则陈旧 lease 被心跳永久续期、
        # gpu_id 永远无法再派发（require_fresh=True 拒绝复用）。
        self._owned_fencing_tokens: dict[str, str] = {}
        self.high_mode_sampler = self.high_mode_sampler or _default_high_mode_sampler
        self.resident_mode_applier = self.resident_mode_applier or _default_resident_mode_applier
        self._last_high_eligible: bool | None = None

    def run_once(self, db: Session, *, now: datetime | None = None) -> int:
        """Recover stuck executing routes, dispatch one route per gpu, heartbeat."""
        now = now or naive_db_now()
        if self.high_resident_enabled:
            self._sync_high_resident_mode()
        sla_failed = self._fail_sla_expired_raptor_jobs(db, now=now)
        if sla_failed:
            db.commit()
            logger.warning("gpu raptor SLA failed count=%s", sla_failed)
        recovered = self._recover_stuck_executing_routes(db, now=now)
        if recovered:
            logger.warning("recovered %s stuck executing gpu route(s)", recovered)
        dispatched = 0
        for gpu_id in self.gpu_ids:
            lease = (
                db.query(GpuSchedulerLease)
                .filter(GpuSchedulerLease.gpu_id == gpu_id)
                .first()
            )
            try:
                result = dispatch_next_gpu_route(
                    db,
                    owner_id=self.owner_id,
                    gpu_id=gpu_id,
                    now=now,
                    publish=None,
                    publishers=self.publishers,
                    ttl_seconds=self.ttl_seconds,
                    current_model_group=lease.model_group if lease is not None else None,
                    current_batch_size=lease.batch_size if lease is not None else 0,
                    batch_started_at=lease.batch_started_at if lease is not None else None,
                )
            except Exception:
                logger.exception("gpu scheduler dispatch failed gpu_id=%s", gpu_id)
                db.rollback()
                continue
            if result is not None:
                self._owned_fencing_tokens[gpu_id] = result.lease.fencing_token
                dispatched += 1
                logger.info(
                    "gpu route dispatched gpu_id=%s job_kind=%s job_id=%s lease_id=%s",
                    gpu_id,
                    result.candidate.job_kind,
                    result.candidate.job_id,
                    result.lease.id,
                )
        self._heartbeat_owned_leases(db, now=now)
        return dispatched

    def _fail_sla_expired_raptor_jobs(self, db: Session, *, now: datetime) -> int:
        """spec §7.3 / SC-164-005：RAPTOR 15 分钟 SLA 的 failed/人工处置分支。

        规则保守：SLA 判定带一个调度 tick 的宽限（aging 到达 900s 后必须至少
        有一个完整 tick 机会被派发）；仅当 job 已等待 >= 阈值、route 未在派发/
        执行中、且**没有任何 active lease**（GPU 空闲/设备不可用/模型切换失败）
        时置 failed 并记录原因；GPU 正被其他 job 占用时只靠 aging 提升优先级，
        不误杀排队任务。
        """
        from models.file import File as FileModel
        from models.kb_post_job import KbPostJob
        from services.gpu_scheduler_persistence import (
            LEASE_ACTIVE,
            OUTBOX_EXECUTING,
            OUTBOX_PUBLISHED,
            OUTBOX_QUEUED,
            ack_queued_gpu_route_for_terminal,
            find_active_lease_for_job,
            find_gpu_route,
        )
        from services.kb_post_service import (
            JOB_ERROR as POST_JOB_ERROR,
            JOB_QUEUED as POST_QUEUED,
            JOB_WAITING_GPU as POST_WAITING_GPU,
            POST_STATUS_FAILED,
        )

        cutoff = now - timedelta(seconds=RAPTOR_MAX_WAIT_SEC + int(self.tick_seconds))
        busy = (
            db.query(GpuSchedulerLease)
            .filter(GpuSchedulerLease.state == LEASE_ACTIVE)
            .first()
        )
        jobs = (
            db.query(KbPostJob)
            .filter(
                KbPostJob.status.in_((POST_QUEUED, POST_WAITING_GPU)),
                KbPostJob.created_at <= cutoff,
            )
            .all()
        )
        failed = 0
        for job in jobs:
            route = find_gpu_route(db, job_kind="raptor", job_id=job.id)
            if route is not None and route.state in (OUTBOX_PUBLISHED, OUTBOX_EXECUTING):
                continue
            if busy is not None or find_active_lease_for_job(db, job_id=job.id) is not None:
                continue
            msg = (
                "raptor_sla_max_wait_exceeded: "
                f"created_at={job.created_at} waited={int((now - job.created_at).total_seconds())}s "
                f"> {RAPTOR_MAX_WAIT_SEC + int(self.tick_seconds)}s gpu_idle=yes"
            )
            job.status = POST_JOB_ERROR
            job.last_error = msg[:2000]
            file_row = db.get(FileModel, job.file_id) if job.file_id is not None else None
            if file_row is not None:
                file_row.kb_post_status = POST_STATUS_FAILED
                file_row.kb_post_error = msg[:2000]
            if route is not None and route.state == OUTBOX_QUEUED:
                ack_queued_gpu_route_for_terminal(db, job_kind="raptor", job_id=job.id)
            logger.error(
                "gpu raptor SLA failed job_id=%s file_id=%s waited=%ss reason=%s",
                job.id,
                job.file_id,
                int((now - job.created_at).total_seconds()),
                msg[:500],
            )
            failed += 1
        return failed

    def _sync_high_resident_mode(self) -> None:
        """每 tick 采样 High 档并按判定结果启停双模型组常驻（164 §5.4/§11.1）。

        采样失败或探针非 ok 一律 fail-closed：关闭常驻，保持串行，不得
        以“调用已返回”推断显存已释放。
        """
        try:
            snapshot = self.high_mode_sampler()
        except Exception:
            logger.exception("gpu high mode sampling failed; resident mode disabled")
            self.resident_mode_applier(False)
            self._last_high_eligible = False
            return
        gpu = snapshot.get("gpu") or {}
        high_eligible = bool(gpu.get("high_eligible"))
        self.resident_mode_applier(high_eligible)
        if high_eligible == self._last_high_eligible:
            return
        self._last_high_eligible = high_eligible
        if high_eligible:
            logger.info("gpu high resident mode enabled")
        else:
            reason = gpu.get("degradation_reason") or gpu.get("reason_code") or HIGH_DEGRADATION_WARMUP
            logger.warning("gpu high resident mode disabled reason=%s", reason)

    def _recover_stuck_executing_routes(self, db: Session, *, now: datetime) -> int:
        """Recover executing/published routes orphaned by a dead execution round.

        consumer 崩溃后重投递消息只能恢复「job 终态 / waiting_gpu」两种情况；
        调度循环按 job 当前状态与 lease 心跳兜底收尾：

        - 终态：ack route 并释放 lease（执行已结束，仅缺 ack/释放）；
        - waiting_gpu：退回 queued 并释放 lease，等待重新发布；
        - running/queued 且绑定 lease 心跳已停止（或 lease 缺失）：执行轮
          liveness 丢失；心跳停止的 active lease 必须先由 watchdog 确认 GPU
          进程为空（或已收到 release_ack / 累计两次空确认）才回收，避免 loop
          停滞或双 worker 场景下回收仍在执行的轮次（164 §5.5）；
        - running/queued 且 lease 心跳新鲜：执行轮仍存活，一律不回收，
          避免并发 GPU 执行。

        心跳只由本进程持有的 fencing token 续期（见
        ``_heartbeat_owned_leases``），因此重启后旧 lease 心跳必然停止，
        本方法在 watchdog 确认后自愈。
        """
        from models.gpu_scheduler import GpuSchedulerOutbox
        from services.gpu_scheduler_persistence import (
            LEASE_ACTIVE,
            OUTBOX_ACKED,
            OUTBOX_EXECUTING,
            OUTBOX_PUBLISHED,
            OUTBOX_QUEUED,
            ack_gpu_route_for_terminal,
            find_active_lease_for_job,
            find_gpu_route,
            recover_gpu_route_for_requeue,
            release_gpu_lease_for_job,
            release_gpu_lease_if_owned,
            reopen_gpu_route,
            rollback_gpu_batch_on_defer,
        )
        from services.kb_extract_service import (
            JOB_DONE as EXTRACT_DONE,
            JOB_ERROR as EXTRACT_ERROR,
            JOB_RUNNING as EXTRACT_RUNNING,
            JOB_WAITING_GPU as EXTRACT_WAITING_GPU,
        )
        from services.kb_post_service import (
            JOB_DONE as POST_DONE,
            JOB_ERROR as POST_ERROR,
            JOB_RUNNING as POST_RUNNING,
            JOB_WAITING_GPU as POST_WAITING_GPU,
        )

        stale_seconds = 2 * self.ttl_seconds
        routes = (
            db.query(GpuSchedulerOutbox)
            .filter(GpuSchedulerOutbox.state.in_((OUTBOX_EXECUTING, OUTBOX_PUBLISHED)))
            .all()
        )
        recovered = 0
        watchdog_recorded = False
        for route in routes:
            if route.job_kind == "mineru":
                from models.kb_extract_job import KbExtractJob

                job = db.get(KbExtractJob, int(route.job_id))
                terminal = job is not None and job.status in (EXTRACT_DONE, EXTRACT_ERROR)
                deferred = job is not None and job.status == EXTRACT_WAITING_GPU
                running = job is not None and job.status == EXTRACT_RUNNING
            elif route.job_kind == "raptor":
                from models.kb_post_job import KbPostJob

                job = db.get(KbPostJob, int(route.job_id))
                terminal = job is not None and job.status in (POST_DONE, POST_ERROR)
                deferred = job is not None and job.status == POST_WAITING_GPU
                running = job is not None and job.status == POST_RUNNING
            else:
                continue
            if route.state == OUTBOX_EXECUTING and (terminal or deferred):
                try:
                    with db.begin_nested():
                        if terminal:
                            recovered_here = ack_gpu_route_for_terminal(
                                db,
                                job_kind=route.job_kind,
                                job_id=route.job_id,
                                owner_id=self.owner_id,
                            )
                        else:
                            recovered_here = recover_gpu_route_for_requeue(
                                db,
                                job_kind=route.job_kind,
                                job_id=route.job_id,
                                owner_id=self.owner_id,
                                rollback_batch=True,
                            )
                except Exception:
                    logger.exception(
                        "gpu route executing recovery failed job_kind=%s job_id=%s",
                        route.job_kind,
                        route.job_id,
                    )
                    continue
                if not recovered_here:
                    continue
                recovered += 1
                logger.warning(
                    "gpu route executing recovered job_kind=%s job_id=%s "
                    "terminal=%s deferred=%s",
                    route.job_kind,
                    route.job_id,
                    terminal,
                    deferred,
                )
                continue

            lease = find_active_lease_for_job(db, job_id=route.job_id)
            if lease is None:
                # 无 lease：不存在需要 watchdog 确认的 executing lease，按
                # 原逻辑恢复（避免无租约 route 永久卡死）。
                pass
            else:
                if not _lease_heartbeat_stale(
                    lease, now=now, stale_seconds=stale_seconds
                ):
                    # 执行轮仍存活（fresh lease）或 claim 后 running 提交前
                    # 的瞬态窗口：不得回收，否则并发 GPU 执行。
                    continue
                confirmed, recorded = self._watchdog_confirms_idle_gpu(
                    db,
                    lease=lease,
                    now=now,
                    job_kind=route.job_kind,
                )
                watchdog_recorded = watchdog_recorded or recorded
                if not confirmed:
                    logger.warning(
                        "gpu route lease heartbeat stale but GPU not confirmed "
                        "idle; recovery blocked job_kind=%s job_id=%s state=%s",
                        route.job_kind,
                        route.job_id,
                        route.state,
                    )
                    continue
            # 执行轮已死（lease 心跳停止或缺失）：恢复 job/route/lease。
            try:
                with db.begin_nested():
                    if running:
                        if route.job_kind == "mineru":
                            from services.kb_extract_service import (
                                requeue_stale_running_extract_job,
                            )

                            requeue_stale_running_extract_job(
                                db,
                                job,
                                now=now,
                                recover_route=False,
                            )
                        else:
                            from services.kb_post_service import (
                                requeue_stale_running_post_job,
                            )

                            requeue_stale_running_post_job(
                                db,
                                job,
                                now=now,
                                recover_route=False,
                            )
                    if terminal:
                        recovered_here = ack_gpu_route_for_terminal(
                            db,
                            job_kind=route.job_kind,
                            job_id=route.job_id,
                            owner_id=self.owner_id,
                        )
                    elif route.state == OUTBOX_EXECUTING:
                        # 同一 job 被 requeue 后仍会重新发布；批边界按 job_id 计数
                        # （spec §7.3），须回退本轮计数，避免 crash 恢复后重复计槽。
                        # watchdog 已清空 active_job_id 时按 gpu_id+fencing token
                        # 定位原执行轮。
                        recovered_here = recover_gpu_route_for_requeue(
                            db,
                            job_kind=route.job_kind,
                            job_id=route.job_id,
                            owner_id=self.owner_id,
                            rollback_batch=True,
                            gpu_id=lease.gpu_id if lease is not None else None,
                            fencing_token=lease.fencing_token if lease is not None else None,
                        )
                    else:
                        reopened = reopen_gpu_route(db, outbox_id=route.id)
                        # published route 从未进入 executing：本轮 dispatch
                        # 计入的批计数对应未执行轮次，回退一格（P2 一致性）。
                        if lease is not None:
                            rollback_gpu_batch_on_defer(
                                db,
                                job_id=route.job_id,
                                owner_id=self.owner_id,
                                gpu_id=lease.gpu_id,
                                fencing_token=lease.fencing_token,
                            )
                        release_gpu_lease_for_job(
                            db,
                            job_id=route.job_id,
                            owner_id=self.owner_id,
                        )
                        recovered_here = reopened is not None
            except Exception:
                logger.exception(
                    "gpu route stale-lease recovery failed job_kind=%s job_id=%s",
                    route.job_kind,
                    route.job_id,
                )
                continue
            if not recovered_here:
                continue
            recovered += 1
            logger.warning(
                "gpu route recovered after dead lease job_kind=%s job_id=%s "
                "state=%s running=%s",
                route.job_kind,
                route.job_id,
                route.state,
                running,
            )

        # 兜底：心跳停止的 active lease 若未绑定 executing/published route
        # （route 已 ack/queued/缺失），直接释放，避免陈旧租约占用 gpu_id。
        stale_cutoff = now - timedelta(seconds=stale_seconds)
        stale_leases = (
            db.query(GpuSchedulerLease)
            .filter(
                GpuSchedulerLease.owner_id == self.owner_id,
                GpuSchedulerLease.state == LEASE_ACTIVE,
                or_(
                    GpuSchedulerLease.heartbeat_at.is_(None),
                    GpuSchedulerLease.heartbeat_at <= stale_cutoff,
                ),
            )
            .all()
        )
        for lease in stale_leases:
            if lease.active_job_id is not None:
                route = None
                for kind in ("mineru", "raptor"):
                    route = find_gpu_route(db, job_kind=kind, job_id=lease.active_job_id)
                    if route is not None:
                        break
                if route is not None and route.state in (OUTBOX_EXECUTING, OUTBOX_PUBLISHED):
                    # 已由上面的 route 扫描在同一事务内处理。
                    continue
            try:
                with db.begin_nested():
                    released = release_gpu_lease_if_owned(
                        db,
                        gpu_id=lease.gpu_id,
                        owner_id=self.owner_id,
                        now=now,
                    )
            except Exception:
                logger.exception(
                    "gpu stale lease release failed gpu_id=%s lease_id=%s",
                    lease.gpu_id,
                    lease.id,
                )
                continue
            if not released:
                continue
            recovered += 1
            logger.warning(
                "gpu stale lease released gpu_id=%s lease_id=%s active_job_id=%s",
                lease.gpu_id,
                lease.id,
                lease.active_job_id,
            )
        if recovered or watchdog_recorded:
            db.commit()
        return recovered

    def _watchdog_confirms_idle_gpu(
        self,
        db: Session,
        *,
        lease: GpuSchedulerLease,
        now: datetime,
        job_kind: str,
    ) -> tuple[bool, bool]:
        """Return ``(confirmed, recorded)`` for reclaiming a stale executing lease.

        ``confirmed`` True 时允许回收（release_ack 已收到，或 watchdog 已累计
        两次“旧执行轮已退出”确认）。``recorded`` True 表示本次调用新记录了一
        次确认（调用方必须提交，否则确认丢失）。

        确认依据是执行轮权威状态（``gpu_round_idle``）：MinerU 轮次由 sidecar
        报告其 active execution 已结束；RAPTOR 轮次与 scheduler 进程共存亡。
        WHB 实测 nvidia-smi 进程采样在 Ollama 常驻 + sidecar 常驻 CUDA 上下文
        下不可达，不能作为确认依据（164 §5.5 T-9 修正）。
        """
        from services.gpu_scheduler_persistence import (
            WATCHDOG_CONFIRMATIONS_REQUIRED,
            record_watchdog_empty_confirmation,
        )

        if lease.release_ack_at is not None:
            return True, False
        if (lease.watchdog_empty_confirmations or 0) >= WATCHDOG_CONFIRMATIONS_REQUIRED:
            return True, False
        if not gpu_round_idle(job_kind=job_kind, lease=lease):
            # 旧执行轮仍存活（或探测失败）：不得记录确认，保持 recovery_blocked。
            return False, False
        with db.begin_nested():
            confirmed = record_watchdog_empty_confirmation(db, lease, now=now)
        return confirmed, True

    def run_forever(self) -> None:
        if not GPU_SCHEDULER_ENABLED:
            raise RuntimeError(
                "GPU_SCHEDULER_ENABLED=false: scheduler loop must not run "
                "while old extract/post consumers still execute GPU work"
            )
        if self.high_resident_enabled:
            # SC-164-008：预热阶段必须每秒采样；调度 tick 默认 5s，无法满足，
            # 因此为 High 判定启独立 1Hz daemon 采样线程，与调度节奏解耦。
            threading.Thread(
                target=self._high_sampler_forever,
                name="gpu-high-sampler",
                daemon=True,
            ).start()
        while True:
            try:
                db = SessionLocal()
                try:
                    self.run_once(db)
                finally:
                    db.close()
            except Exception:
                logger.exception("gpu scheduler tick failed")
            time.sleep(self.tick_seconds)

    def _high_sampler_forever(self) -> None:
        """1Hz High 档采样循环：每 1s 重新采样并应用常驻开关（fail-closed）。"""
        while True:
            try:
                self._sync_high_resident_mode()
            except Exception:
                logger.exception("gpu high sampler tick failed")
            time.sleep(HIGH_WARMUP_SAMPLE_SEC)

    def _heartbeat_owned_leases(self, db: Session, *, now: datetime) -> None:
        """Heartbeat only leases this process actually acquired.

        重启后的新进程没有上一进程的 fencing token（``_owned_fencing_tokens``
        为空），因此不会续期旧 lease；旧 lease 心跳停止后由
        ``_recover_stuck_executing_routes`` 在 2×TTL 内回收。
        """
        heartbeated = False
        for gpu_id in self.gpu_ids:
            fencing_token = self._owned_fencing_tokens.get(gpu_id)
            if fencing_token is None:
                continue
            try:
                with db.begin_nested():
                    owned = heartbeat_gpu_lease_if_owned(
                        db,
                        gpu_id=gpu_id,
                        owner_id=self.owner_id,
                        fencing_token=fencing_token,
                        ttl_seconds=self.ttl_seconds,
                        now=now,
                    )
                if not owned:
                    logger.info(
                        "gpu lease no longer owned by this scheduler gpu_id=%s",
                        gpu_id,
                    )
                    continue
                heartbeated = True
            except Exception:
                logger.exception(
                    "gpu lease heartbeat failed gpu_id=%s",
                    gpu_id,
                )
        if heartbeated:
            db.commit()
