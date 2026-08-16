# Copyright (c) 2026 徐泽宇
"""Scheduler-owned RabbitMQ consumer for ``filex.gpu.*`` routes (164 §6).

Only the GPU scheduler consumes these queues. A route message is published by
the dispatch loop only after it fences a fresh ``gpu_leases`` row, so this
consumer never executes a job without a lease. It claims the published outbox,
reuses the existing extract/post execution paths, and only then acks the
message; durability and duplicate protection live in the outbox state machine
(``idempotency_key`` + ``handover_epoch``), not in RabbitMQ unack state.
"""

from __future__ import annotations

import logging
import threading
import time

import pika
import pika.exceptions as pika_exc
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from config import GPU_SCHEDULER_ENABLED, GPU_SCHEDULER_OWNER_ID
from database import SessionLocal
from messaging.gpu_queues import (
    QUEUE_GPU_MINERU,
    QUEUE_GPU_RAPTOR,
    declare_gpu_topology,
    open_blocking_connection,
    parse_gpu_route_body,
)
from messaging.kb_mineru_rpc import (
    bind_consumer_keepalive_connection,
    reset_consumer_keepalive_connection,
)
from models.gpu_scheduler import GpuSchedulerOutbox
from services.gpu_scheduler_persistence import (
    OUTBOX_ACKED,
    OUTBOX_EXECUTING,
    OUTBOX_PUBLISHED,
    OUTBOX_QUEUED,
    ack_gpu_route,
    enqueue_gpu_route,
    find_gpu_route,
    rollback_gpu_batch_on_defer,
    release_gpu_execution,
    release_gpu_lease_for_job,
    reopen_gpu_route,
)
from models.kb_extract_job import KbExtractJob
from models.kb_post_job import KbPostJob
from services.kb_extract_service import JOB_DONE as EXTRACT_DONE
from services.kb_extract_service import JOB_ERROR as EXTRACT_ERROR
from services.kb_extract_service import JOB_QUEUED as EXTRACT_QUEUED
from services.kb_extract_service import JOB_WAITING_GPU as EXTRACT_WAITING_GPU
from services.kb_post_service import JOB_DONE as POST_DONE
from services.kb_post_service import JOB_ERROR as POST_ERROR
from services.kb_post_service import JOB_QUEUED as POST_QUEUED
from services.kb_post_service import JOB_WAITING_GPU as POST_WAITING_GPU
from services.license_service import require_license_or_wait
from utils.timezone import beijing_now

logger = logging.getLogger(__name__)

GPU_SCHEDULER_CONSUMER_RECONNECT_SEC = 3
# 迁移期历史消息可能在 DB commit 前被旧发布器投递；route 仍为 queued 时
# bounded requeue，超限后丢弃（route 已持久化，dispatch loop 会重新发布）。
GPU_ROUTE_WAITING_MAX_REQUEUE = 8
# publish-before-commit 下，与 dispatch 同进程的空闲 consumer 几乎必然在
# dispatch commit 前收到消息；等待有界，防止 dispatch 线程异常持有锁时
# consumer 永久阻塞（超时后走 bounded requeue/drop 兜底）。
DISPATCH_COMMIT_LOCK_TIMEOUT_SEC = 5.0
_waiting_requeue_counts: dict[tuple[str, str], int] = {}
_waiting_requeue_lock = threading.Lock()


def _log_time_beijing() -> str:
    return beijing_now().strftime("%Y-%m-%d %H:%M:%S")


def handle_gpu_route_message(db, conn, payload: dict) -> tuple[str, object | None]:
    """Claim and execute one GPU route; return ``(outcome, post_token)``.

    Outcomes:
      ``backfilled``  historical message, outbox rebuilt; waits for dispatch
      ``acked``       duplicate of an already-finished route
      ``stale_epoch``  old handover epoch; must not claim the job
      ``waiting``      route still ``queued``; dispatch will publish it later
      ``deferred``     job ended ``waiting_gpu``; route reopened for re-dispatch
      ``executed``     route claimed and executed under the leased outbox
    """
    job_kind = str(payload["job_kind"])
    job_id = str(payload["job_id"])
    idempotency_key = str(payload.get("idempotency_key") or f"{job_kind}:{job_id}:0")
    handover_epoch = int(payload.get("handover_epoch") or 0)

    route = db.execute(
        select(GpuSchedulerOutbox).where(
            GpuSchedulerOutbox.idempotency_key == idempotency_key
        )
    ).scalar_one_or_none()
    if route is None:
        route = find_gpu_route(db, job_kind=job_kind, job_id=job_id)
    if route is None:
        enqueue_gpu_route(
            db,
            job_kind=job_kind,
            job_id=job_id,
            file_id=payload.get("file_id"),
            idempotency_key=idempotency_key,
            payload=dict(payload),
            handover_epoch=handover_epoch,
        )
        db.commit()
        return "backfilled", None
    if route.state == OUTBOX_ACKED:
        release_gpu_lease_for_job(
            db,
            job_id=job_id,
            owner_id=GPU_SCHEDULER_OWNER_ID,
        )
        db.commit()
        return "acked", None
    if int(route.handover_epoch or 0) != handover_epoch:
        db.commit()
        return "stale_epoch", None
    if route.state == OUTBOX_EXECUTING:
        # 执行轮崩溃后的重投递：route 已 executing，本消息无法再次 claim。
        if _job_is_terminal(db, job_kind=job_kind, job_id=job_id):
            # 终态已提交但 ack/释放前崩溃：ack route 并释放 lease，dispatch
            # loop 可继续调度下一 job，GPU 不再被心跳永久占用。
            ack_gpu_route(db, outbox_id=route.id)
            release_gpu_lease_for_job(
                db,
                job_id=job_id,
                owner_id=GPU_SCHEDULER_OWNER_ID,
            )
            db.commit()
            return "executed", None
        if _job_is_waiting_gpu(db, job_kind=job_kind, job_id=job_id):
            # 执行轮在 defer 收尾前崩溃：补完 execution -> published -> queued
            # 并释放 lease，交还调度循环重新发布。
            release_gpu_execution(db, outbox_id=route.id)
            reopen_gpu_route(db, outbox_id=route.id)
            rollback_gpu_batch_on_defer(
                db,
                job_id=job_id,
                owner_id=GPU_SCHEDULER_OWNER_ID,
            )
            release_gpu_lease_for_job(
                db,
                job_id=job_id,
                owner_id=GPU_SCHEDULER_OWNER_ID,
            )
            db.commit()
            return "deferred", None
        # 非终态：可能另一执行轮仍在进行，ack 但不释放 lease，避免并发 GPU
        # 执行；job 层 stale 回收负责重新排队。
        db.commit()
        return "duplicate", None
    if route.state != "published":
        # 尚未由 dispatch 完成发布；保持 queued/claimed，等待下一 tick。
        db.commit()
        return "waiting", None

    if job_kind == "mineru":
        from messaging.kb_extract_consumer import _handle_job as _handle_extract_job

        claimed_route_id = _handle_extract_job(db, int(job_id), conn, _from_gpu_scheduler=True)
        token = None
    elif job_kind == "raptor":
        from messaging.kb_post_consumer import _handle_job as _handle_post_job

        token, claimed_route_id = _handle_post_job(db, int(job_id), conn, _from_gpu_scheduler=True)
    else:
        raise ValueError(f"unsupported gpu route job_kind={job_kind!r}")

    claimed_this_round = claimed_route_id is not None and claimed_route_id == route.id
    if claimed_this_round and _job_is_waiting_gpu(db, job_kind=job_kind, job_id=job_id):
        # 执行轮结束但仍需 GPU（运行时模型组忙）：把 route 退回 queued，
        # 释放本次 dispatch lease，由调度循环重新取得租约后再次发布。
        reopen_gpu_route(db, outbox_id=route.id)
        rollback_gpu_batch_on_defer(
            db,
            job_id=job_id,
            owner_id=GPU_SCHEDULER_OWNER_ID,
        )
        release_gpu_lease_for_job(
            db,
            job_id=job_id,
            owner_id=GPU_SCHEDULER_OWNER_ID,
        )
        db.commit()
        return "deferred", token
    route_state = db.execute(
        select(GpuSchedulerOutbox.state).where(GpuSchedulerOutbox.id == route.id)
    ).scalar_one()
    if (
        route_state == OUTBOX_EXECUTING
        and claimed_this_round
        and _job_is_deferred_after_claim(db, job_kind=job_kind, job_id=job_id)
    ):
        # 本轮 claim 成功后 handler 走了 defer 路径（如 extract
        # active_job_on_file）：job 仍为 queued、未进入终态，route 停留在
        # executing。此时执行轮已结束，先释放 execution 再退回 queued，
        # 并释放本次 dispatch lease，等待调度循环重新发布。
        release_gpu_execution(db, outbox_id=route.id)
        reopen_gpu_route(db, outbox_id=route.id)
        rollback_gpu_batch_on_defer(
            db,
            job_id=job_id,
            owner_id=GPU_SCHEDULER_OWNER_ID,
        )
        release_gpu_lease_for_job(
            db,
            job_id=job_id,
            owner_id=GPU_SCHEDULER_OWNER_ID,
        )
        db.commit()
        return "deferred", token
    if route_state == OUTBOX_EXECUTING:
        if _job_is_terminal(db, job_kind=job_kind, job_id=job_id):
            # 执行轮已提交终态但未及 ack/释放即崩溃：route 停留在 executing，
            # 消息重投递后无法再 claim。job 不再需要执行，释放 lease 即可让
            # dispatch loop 继续调度下一个 job，避免 GPU 永久占用。
            release_gpu_lease_for_job(
                db,
                job_id=job_id,
                owner_id=GPU_SCHEDULER_OWNER_ID,
            )
            db.commit()
            return "executed", token
        # 本轮未 claim 成功（另一个执行轮仍在进行）：ack 消息但不得释放 lease，
        # 否则 dispatch loop 会取得 fresh lease 并启动第二个并发 GPU job。
        db.commit()
        return "duplicate", token
    release_gpu_lease_for_job(
        db,
        job_id=job_id,
        owner_id=GPU_SCHEDULER_OWNER_ID,
    )
    db.commit()
    return "executed", token


def _job_is_waiting_gpu(db, *, job_kind: str, job_id: str) -> bool:
    if job_kind == "mineru":
        row = db.get(KbExtractJob, int(job_id))
        return row is not None and row.status == EXTRACT_WAITING_GPU
    row = db.get(KbPostJob, int(job_id))
    return row is not None and row.status == POST_WAITING_GPU


def _job_is_deferred_after_claim(db, *, job_kind: str, job_id: str) -> bool:
    """route 仍 executing 且 job 仍为 queued 时，说明本轮 claim 后 handler
    未执行完成也未释放 execution（defer 路径）；job 为 running 则可能是其他
    执行轮持有，不得收回 route 或释放 lease。"""
    if job_kind == "mineru":
        row = db.get(KbExtractJob, int(job_id))
        return row is not None and row.status == EXTRACT_QUEUED
    row = db.get(KbPostJob, int(job_id))
    return row is not None and row.status == POST_QUEUED


def _job_is_terminal(db, *, job_kind: str, job_id: str) -> bool:
    """job 是否已进入 done/error 终态（无需再执行）。"""
    if job_kind == "mineru":
        row = db.get(KbExtractJob, int(job_id))
        return row is not None and row.status in (EXTRACT_DONE, EXTRACT_ERROR)
    row = db.get(KbPostJob, int(job_id))
    return row is not None and row.status in (POST_DONE, POST_ERROR)


def _drop_waiting_requeue_count(job_kind: str, job_id: str) -> None:
    with _waiting_requeue_lock:
        _waiting_requeue_counts.pop((job_kind, job_id), None)


def _wait_for_dispatch_commit(
    db, *, job_kind: str, job_id: str
) -> str | None:
    """Block until the in-flight dispatch transaction commits or rolls back.

    publish-before-commit 设计下，与 dispatch 同进程的空闲 consumer 会在
    dispatch commit 前收到消息；直接 bounded requeue 会在 commit 前耗尽，
    ``_reconcile_waiting_route_before_drop`` 把刚提交的 published route 退回
    queued 并释放 lease，形成每 tick 重发、job 永不执行的循环（WHB T-9
    实测）。本函数用 FOR UPDATE 与 dispatch 事务串行化：dispatch commit 后
    读到 ``published`` 即可正常 claim/执行；rollback 后保持 ``queued``。
    锁等待有界（``SET LOCAL lock_timeout``）；dispatch 线程异常持有锁时抛出
    OperationalError，由调用方走 bounded requeue/drop 兜底。
    """
    db.rollback()
    db.execute(
        text("SET LOCAL lock_timeout = :timeout"),
        {"timeout": f"{DISPATCH_COMMIT_LOCK_TIMEOUT_SEC}s"},
    )
    row = (
        db.execute(
            select(GpuSchedulerOutbox)
            .where(
                GpuSchedulerOutbox.job_kind == job_kind,
                GpuSchedulerOutbox.job_id == str(job_id),
            )
            .order_by(GpuSchedulerOutbox.id.desc())
            .limit(1)
            .with_for_update()
        )
        .scalar_one_or_none()
    )
    db.commit()
    return row.state if row is not None else None


def _reconcile_waiting_route_before_drop(db, *, job_kind: str, job_id: str) -> None:
    """丢弃 waiting 消息前，与 dispatch 事务串行化并修正已提交的 published 状态。

    publish-before-commit 下，consumer 可能在 dispatch commit 前收到消息并
    bounded requeue。若恰在最后一次 requeue 后 dispatch 才 commit，消息被丢弃
    而 route 已 published、lease 已 active（且被心跳续期），GPU 会永久卡死。
    这里用 FOR UPDATE 等待 dispatch 事务结束：commit 成功则把 route 收回
    queued 并释放 lease（dispatch loop 重新发布）；rollback 则保持 queued，
    直接丢弃消息即可。正常路径下 waiting 消息会先由
    ``_wait_for_dispatch_commit`` 与 dispatch 事务串行化，本函数仅作为
    dispatch 异常持有锁超时后的兜底。
    """
    row = db.execute(
        select(GpuSchedulerOutbox)
        .where(
            GpuSchedulerOutbox.job_kind == job_kind,
            GpuSchedulerOutbox.job_id == str(job_id),
        )
        .order_by(GpuSchedulerOutbox.id.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None or row.state != OUTBOX_PUBLISHED:
        return
    row.state = OUTBOX_QUEUED
    row.published_at = None
    release_gpu_lease_for_job(
        db,
        job_id=str(job_id),
        owner_id=GPU_SCHEDULER_OWNER_ID,
    )
    db.commit()
    logger.warning(
        "gpu route waiting drop recovered published route job_kind=%s job_id=%s",
        job_kind,
        job_id,
    )


def _on_message(ch, method, _properties, body: bytes) -> None:
    try:
        payload = parse_gpu_route_body(body)
    except Exception:
        logger.warning("invalid gpu route message body: %r", body[:200])
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    conn = ch.connection
    keepalive_token = bind_consumer_keepalive_connection(conn)
    db = SessionLocal()
    token = None
    start_time_str = _log_time_beijing()
    try:
        if not require_license_or_wait(db):
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return
        outcome, token = handle_gpu_route_message(db, conn, payload)
        key = (str(payload["job_kind"]), str(payload["job_id"]))
        if outcome == "waiting":
            # 早到消息：先与 dispatch 事务串行化，避免 bounded requeue 在
            # dispatch commit 前耗尽，把已发布 route 退回 queued 形成死循环。
            try:
                settled = _wait_for_dispatch_commit(
                    db, job_kind=key[0], job_id=key[1]
                )
            except OperationalError:
                db.rollback()
                settled = None
            if settled == OUTBOX_PUBLISHED:
                # dispatch 已 commit：重入 handler 正常 claim/执行。
                _drop_waiting_requeue_count(*key)
                outcome, token = handle_gpu_route_message(db, conn, payload)
            elif settled is None:
                # route 已不存在（ack/迁移竞态）：丢弃消息，状态由持久化收敛。
                with _waiting_requeue_lock:
                    _waiting_requeue_counts.pop(key, None)
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return
            # 其余（queued/executing/锁定超时）：dispatch 未 commit 或已回滚，
            # outcome 保持 waiting，走 bounded requeue/drop 兜底。
        if outcome == "waiting":
            with _waiting_requeue_lock:
                count = _waiting_requeue_counts.get(key, 0) + 1
                _waiting_requeue_counts[key] = count
            if count >= GPU_ROUTE_WAITING_MAX_REQUEUE:
                with _waiting_requeue_lock:
                    _waiting_requeue_counts.pop(key, None)
                logger.warning(
                    "gpu route still queued after %d requeues; dropping "
                    "job_kind=%s job_id=%s (route persists in DB, dispatch loop re-publishes)",
                    count,
                    key[0],
                    key[1],
                )
                try:
                    _reconcile_waiting_route_before_drop(
                        db,
                        job_kind=key[0],
                        job_id=key[1],
                    )
                except OperationalError:
                    db.rollback()
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                    return
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return
        _drop_waiting_requeue_count(*key)
        logger.info(
            "gpu route consumed job_kind=%s job_id=%s outcome=%s start=%s",
            payload["job_kind"],
            payload["job_id"],
            outcome,
            start_time_str,
        )
    except OperationalError:
        logger.exception(
            "gpu route job_kind=%s job_id=%s db unavailable, requeue",
            payload.get("job_kind"),
            payload.get("job_id"),
        )
        db.rollback()
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return
    except Exception as exc:
        logger.exception(
            "gpu route job_kind=%s job_id=%s handler error",
            payload.get("job_kind"),
            payload.get("job_id"),
        )
        db.rollback()
        job_kind = str(payload.get("job_kind") or "")
        job_id = payload.get("job_id")
        try:
            if job_kind == "mineru":
                from messaging.kb_extract_consumer import _recover_handler_error

                _recover_handler_error(int(job_id), str(exc), conn)
            else:
                from messaging.kb_post_consumer import _recover_handler_error

                _recover_handler_error(int(job_id), str(exc), conn, token)
        except Exception:
            logger.exception("failed to recover gpu route job_id=%s", job_id)
        # handler 异常后本轮执行结束：无论 retry 还是 DLQ，都释放本次 dispatch lease。
        release_db = SessionLocal()
        try:
            released = release_gpu_lease_for_job(
                release_db,
                job_id=job_id,
                owner_id=GPU_SCHEDULER_OWNER_ID,
            )
            release_db.commit()
            if released:
                logger.info("gpu route lease released after handler error job_id=%s", job_id)
        except Exception:
            logger.exception("failed to release gpu lease after handler error job_id=%s", job_id)
            release_db.rollback()
        finally:
            release_db.close()
    finally:
        db.close()
        reset_consumer_keepalive_connection(keepalive_token)
    ch.basic_ack(delivery_tag=method.delivery_tag)


def run_consumer() -> None:
    """Consume both scheduler-owned GPU route queues (serial prefetch=1)."""
    if not GPU_SCHEDULER_ENABLED:
        raise RuntimeError(
            "GPU_SCHEDULER_ENABLED=false: scheduler consumer must not run "
            "while old extract/post consumers still execute GPU work"
        )
    while True:
        connection: pika.BlockingConnection | None = None
        try:
            connection = open_blocking_connection()
            channel = connection.channel()
            declare_gpu_topology(channel)
            channel.basic_qos(prefetch_count=1)
            for queue in (QUEUE_GPU_MINERU, QUEUE_GPU_RAPTOR):
                channel.basic_consume(
                    queue=queue,
                    on_message_callback=_on_message,
                    auto_ack=False,
                )
            logger.info(
                "gpu scheduler consumer listening on %s, %s (prefetch=1)",
                QUEUE_GPU_MINERU,
                QUEUE_GPU_RAPTOR,
            )
            while connection.is_open:
                gate_db = SessionLocal()
                try:
                    if not require_license_or_wait(gate_db):
                        continue
                finally:
                    gate_db.close()
                connection.process_data_events(time_limit=1)
        except KeyboardInterrupt:
            raise
        except pika_exc.AMQPConnectionError as exc:
            logger.warning("gpu scheduler consumer connection lost (%s); reconnecting", exc)
            time.sleep(GPU_SCHEDULER_CONSUMER_RECONNECT_SEC)
        except Exception:
            logger.exception("gpu scheduler consumer error; reconnecting")
            time.sleep(GPU_SCHEDULER_CONSUMER_RECONNECT_SEC)
        finally:
            if connection is not None:
                try:
                    if connection.is_open:
                        connection.close()
                except Exception:
                    pass
