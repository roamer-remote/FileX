# Copyright (c) 2026 徐泽宇
"""RabbitMQ consumer for KB extract jobs (serial prefetch=1).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta

import pika
import pika.exceptions as pika_exc
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from config import (
    KB_EXTRACT_REPLAY_INTERVAL_SEC,
    KB_EXTRACT_REPLAY_STALE_SEC,
    KB_EXTRACT_RUNNING_STALE_SEC,
)
from database import SessionLocal
from services.license_service import require_license_or_wait
from messaging.kb_extract_publisher import (
    publish_file_extract_notify,
    publish_kb_extract_dlq,
    publish_kb_extract_retry,
)
from messaging.kb_mineru_rpc import (
    bind_consumer_keepalive_connection,
    reset_consumer_keepalive_connection,
)
from messaging.kb_extract_queues import (
    QUEUE_MAIN,
    declare_kb_extract_topology,
    open_blocking_connection,
)
from models.file import File as FileModel
from utils.timezone import beijing_now
from models.kb_extract_job import KbExtractJob
from services.kb_extract_service import (
    JOB_DONE,
    JOB_ERROR,
    JOB_QUEUED,
    JOB_RUNNING,
    JOB_WAITING_GPU,
    STATUS_FAILED,
    STATUS_PENDING,
    get_kb_extract_max_attempts,
    replay_queued_jobs,
    run_extract_job,
)

logger = logging.getLogger(__name__)


def _log_time_beijing() -> str:
    return beijing_now().strftime("%Y-%m-%d %H:%M:%S")

KB_EXTRACT_CONSUMER_RECONNECT_SEC = 3

_replay_stop = threading.Event()
_replay_thread: threading.Thread | None = None



def _publish_extract_notify_safe(
    f: FileModel,
    conn: pika.BlockingConnection,
    *,
    processing_duration_ms: int | None = None,
) -> None:
    try:
        publish_file_extract_notify(
            f,
            connection=conn,
            processing_duration_ms=processing_duration_ms,
        )
    except Exception:
        logger.exception("publish extract notify failed file_id=%s", f.id)


def _handle_job(
    db: Session,
    job_id: int,
    conn: pika.BlockingConnection,
    *,
    _from_gpu_scheduler: bool = False,
) -> int | None:
    """执行一个 extract job；返回本轮 claim 成功的 GPU route id（未 claim 为 None）。

    GPU scheduler 消费端依赖该返回值区分「本轮 claim 后 defer」与「另一个执行轮
    仍在执行」，避免误释放其他 worker 的 execution/lease。
    """
    job = (
        db.query(KbExtractJob)
        .filter(KbExtractJob.id == job_id, KbExtractJob.status.in_((JOB_QUEUED, JOB_WAITING_GPU)))
        .with_for_update()
        .first()
    )
    if not job:
        stale = db.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
        if stale:
            logger.warning(
                "kb extract message for job_id=%s ignored (status=%s, not queued)",
                job_id,
                stale.status,
            )
        else:
            logger.warning("kb extract message for unknown job_id=%s", job_id)
        return None

    from services.gpu_scheduler_persistence import (
        ack_gpu_route,
        claim_gpu_execution,
        find_gpu_route,
        reopen_gpu_route,
        release_gpu_execution,
        release_gpu_lease_for_job,
    )

    gpu_route = find_gpu_route(db, job_kind="mineru", job_id=job.id)
    from config import GPU_SCHEDULER_ENABLED, GPU_SCHEDULER_OWNER_ID

    if (
        GPU_SCHEDULER_ENABLED
        and gpu_route is None
        and not _from_gpu_scheduler
        and _extract_job_uses_mineru(db, job)
    ):
        # 164 §6：GPU 模式下 mineru job 缺失 durable route（迁移期遗留行或
        # provider 在 enqueue 后解析变化）时回查补建，绝不无租约执行 MinerU。
        from services.gpu_scheduler_persistence import enqueue_gpu_route

        enqueue_gpu_route(
            db,
            job_kind="mineru",
            job_id=job.id,
            file_id=job.file_id,
            idempotency_key=f"mineru:{job.id}:0",
            payload={
                "job_id": int(job.id),
                "job_kind": "mineru",
                "file_id": int(job.file_id),
                "attempt": 0,
                "idempotency_key": f"mineru:{job.id}:0",
                "handover_epoch": 0,
            },
        )
        db.commit()
        logger.info("kb extract backfilled mineru route for gpu scheduler job_id=%s", job.id)
        return None

    if GPU_SCHEDULER_ENABLED and gpu_route is not None and not _from_gpu_scheduler:
        # 164 §6：GPU 调度模式下旧 extract consumer 只提交/回查持久化 job，
        # 不执行 GPU。published route 只有在没有任何活跃 dispatch lease
        # （遗留桥接发布）时才退回 queued；scheduler 已取得租约的 route 由
        # scheduler consumer claim/执行，旧 consumer 不得重开或释放 lease，
        # 否则会丢弃 in-flight 消息并触发重派发竞态（164 §6 / P3）。
        if gpu_route.state == "published":
            from services.gpu_scheduler_persistence import (
                find_active_lease_for_job,
            )

            active_lease = find_active_lease_for_job(
                db,
                job_id=job.id,
                owner_id=GPU_SCHEDULER_OWNER_ID,
            )
            if active_lease is None:
                reopened = reopen_gpu_route(db, outbox_id=gpu_route.id)
                if reopened is not None:
                    # 无活跃 lease 时释放是幂等 no-op；保留调用以兜底遗留
                    # 已释放但未清空的状态。
                    release_gpu_lease_for_job(
                        db,
                        job_id=job.id,
                        owner_id=GPU_SCHEDULER_OWNER_ID,
                    )
            else:
                logger.info(
                    "kb extract skip handover reopen: scheduler lease active job_id=%s",
                    job.id,
                )
        db.commit()
        logger.info("kb extract handed over to gpu scheduler job_id=%s", job.id)
        return None

    gpu_route_id = None
    if gpu_route is not None:
        claimed_route = claim_gpu_execution(db, job_kind="mineru", job_id=job.id)
        if claimed_route is None:
            logger.info("kb extract duplicate or unpublished GPU route ignored job_id=%s", job.id)
            db.rollback()
            return None
        gpu_route_id = claimed_route.id

    max_attempts = get_kb_extract_max_attempts()
    start_perf = time.perf_counter()
    run_extract_job(db, job)
    processing_duration_ms = int((time.perf_counter() - start_perf) * 1000)
    db.commit()

    db.refresh(job)
    f = db.query(FileModel).filter(FileModel.id == job.file_id).first()

    if job.status == JOB_DONE:
        if gpu_route_id is not None:
            ack_gpu_route(db, outbox_id=gpu_route_id)
            db.commit()
        if f:
            _publish_extract_notify_safe(
                f,
                conn,
                processing_duration_ms=processing_duration_ms,
            )
        return gpu_route_id
    if job.status in (JOB_WAITING_GPU,):
        if gpu_route_id is not None:
            release_gpu_execution(db, outbox_id=gpu_route_id)
            db.commit()
        if f:
            _publish_extract_notify_safe(f, conn, processing_duration_ms=processing_duration_ms)
        logger.info("kb extract job remains waiting for GPU job_id=%s file_id=%s", job.id, job.file_id)
        return gpu_route_id
    if job.status != JOB_ERROR:
        if f:
            _publish_extract_notify_safe(f, conn)
        return gpu_route_id

    if (job.attempts or 0) < max_attempts:
        if gpu_route_id is not None:
            release_gpu_execution(db, outbox_id=gpu_route_id)
            if _from_gpu_scheduler:
                # GPU 调度模式下 retry 由 dispatch loop 重新发布：route 立即
                # 退回 queued 并递增 handover_epoch，避免 retry 消息依赖旧
                # consumer 交接（旧 consumer 见到活跃 lease 会跳过重开，若
                # 此处不重开，job 会停在 published 卡死）。
                reopen_gpu_route(db, outbox_id=gpu_route_id)
        if f:
            _publish_extract_notify_safe(f, conn)
        job.status = JOB_QUEUED
        if f:
            f.extract_status = STATUS_PENDING
            f.extract_error = None
        db.commit()
        publish_kb_extract_retry(job.id, connection=conn)
        if f:
            _publish_extract_notify_safe(f, conn)
        logger.warning(
            "kb_extract_job_retry_scheduled job_id=%s file_id=%s attempt=%s/%s last_error=%s",
            job.id,
            job.file_id,
            job.attempts,
            max_attempts,
            (job.last_error or "")[:500],
        )
        return gpu_route_id

    publish_kb_extract_dlq(job.id, last_error=job.last_error)
    if gpu_route_id is not None:
        ack_gpu_route(db, outbox_id=gpu_route_id)
    if f:
        f.extract_status = STATUS_FAILED
        db.commit()
        _publish_extract_notify_safe(
            f,
            conn,
            processing_duration_ms=processing_duration_ms,
        )
    logger.error(
        "kb_extract_job_dlq job_id=%s file_id=%s attempts=%s last_error=%s",
        job.id,
        job.file_id,
        job.attempts,
        (job.last_error or "")[:500],
    )
    return gpu_route_id


def _extract_job_uses_mineru(db: Session, job: KbExtractJob) -> bool:
    """Job 运行时是否走 MinerU（显式 provider 或未指定时按运行时默认解析）。"""
    if job.provider == "mineru":
        return True
    if job.provider is not None:
        return False
    f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
    if f is None:
        return False
    from services.kb_pipeline_service import resolve_extract_provider

    return resolve_extract_provider(db, f, explicit_provider=None) == "mineru"


def _recover_handler_error(job_id: int, detail: str, conn: pika.BlockingConnection) -> None:
    db = SessionLocal()
    try:
        from services.gpu_scheduler_persistence import find_gpu_route, release_gpu_execution

        job = db.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
        if not job or job.status != JOB_RUNNING:
            return
        route = find_gpu_route(db, job_kind="mineru", job_id=job_id)
        if route is not None:
            release_gpu_execution(db, outbox_id=route.id)
        max_attempts = get_kb_extract_max_attempts()
        job.attempts = (job.attempts or 0) + 1
        msg = (detail or "kb extract handler failed")[:2000]
        job.last_error = msg
        f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
        if (job.attempts or 0) < max_attempts:
            job.status = JOB_QUEUED
            if f:
                f.extract_status = STATUS_PENDING
                f.extract_error = None
            db.commit()
            publish_kb_extract_retry(job.id, connection=conn)
            if f:
                try:
                    publish_file_extract_notify(f, connection=conn)
                except Exception:
                    logger.exception("publish extract handler retry notify failed file_id=%s", f.id)
            logger.warning(
                "kb_extract_handler_retry job_id=%s file_id=%s attempt=%s/%s",
                job.id,
                job.file_id,
                job.attempts,
                max_attempts,
            )
            return
        job.status = JOB_ERROR
        if f:
            f.extract_status = STATUS_FAILED
            f.extract_error = msg
        db.commit()
        publish_kb_extract_dlq(job.id, last_error=job.last_error)
        if f:
            try:
                publish_file_extract_notify(f, connection=conn)
            except Exception:
                logger.exception("publish extract handler dlq notify failed file_id=%s", f.id)
        logger.error(
            "kb_extract_handler_dlq job_id=%s file_id=%s attempts=%s",
            job.id,
            job.file_id,
            job.attempts,
        )
    except Exception:
        logger.exception("failed to recover kb extract job %s after handler failure", job_id)
        db.rollback()
    finally:
        db.close()


def _on_message(ch, method, _properties, body: bytes) -> None:
    try:
        payload = json.loads(body.decode("utf-8"))
        job_id = int(payload["job_id"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("invalid kb extract message body: %r", body[:200])
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    conn = ch.connection
    keepalive_token = bind_consumer_keepalive_connection(conn)
    db = SessionLocal()
    start_perf = time.perf_counter()
    start_time_str = _log_time_beijing()
    file_id: int | None = None
    result_note = "完成"
    try:
        job_row = db.query(KbExtractJob.file_id).filter(KbExtractJob.id == job_id).first()
        if job_row is not None:
            file_id = int(job_row[0])
        logger.info(
            "【提取消费者】接到提取任务：job_id=%s，file_id=%s，开始时间=%s",
            job_id,
            file_id if file_id is not None else "未知",
            start_time_str,
        )
        if not require_license_or_wait(db):
            result_note = "未执行（license 无效，消息已 requeue）"
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return
        _handle_job(db, job_id, conn)
        job_after = db.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
        if job_after is not None:
            file_id = int(job_after.file_id)
            result_note = f"任务状态={job_after.status}"
    except OperationalError:
        result_note = "失败（数据库不可用，消息已 requeue）"
        logger.exception("kb extract job %s db unavailable, requeue", job_id)
        db.rollback()
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return
    except Exception as exc:
        result_note = "失败（handler 异常，已尝试恢复）"
        logger.exception("kb extract job %s handler error", job_id)
        db.rollback()
        _recover_handler_error(job_id, str(exc), conn)
    finally:
        elapsed_sec = time.perf_counter() - start_perf
        end_time_str = _log_time_beijing()
        logger.info(
            "【提取消费者】提取任务结束：job_id=%s，file_id=%s，结束时间=%s，耗时=%.2f 秒（%.0f 毫秒），%s",
            job_id,
            file_id if file_id is not None else "未知",
            end_time_str,
            elapsed_sec,
            elapsed_sec * 1000,
            result_note,
        )
        db.close()
        reset_consumer_keepalive_connection(keepalive_token)
    ch.basic_ack(delivery_tag=method.delivery_tag)


def _replay_loop() -> None:
    while not _replay_stop.is_set():
        try:
            db = SessionLocal()
            try:
                if not require_license_or_wait(db):
                    continue
                from services.kb_extract_service import reconcile_stale_kb_extract_jobs

                # GPU scheduler 崩溃后 running MinerU job 的 lease 心跳停止，
                # 周期 reconcile 负责重排队并恢复 route/lease（与 post 侧对齐）。
                n_recovered = reconcile_stale_kb_extract_jobs(
                    db,
                    stale_seconds=KB_EXTRACT_RUNNING_STALE_SEC,
                )
                if n_recovered:
                    db.commit()
                    logger.info(
                        "periodic reconciled stale running kb extract job(s) count=%s",
                        n_recovered,
                    )
                n = replay_queued_jobs(db, full=bool(n_recovered))
                if n:
                    logger.info("periodic stale extract replay republished %s job(s)", n)
            finally:
                db.close()
        except Exception:
            logger.exception("periodic kb extract job replay failed")
        _replay_stop.wait(KB_EXTRACT_REPLAY_INTERVAL_SEC)


def start_periodic_replay() -> None:
    if KB_EXTRACT_REPLAY_INTERVAL_SEC <= 0:
        return
    global _replay_thread
    if _replay_thread and _replay_thread.is_alive():
        return
    _replay_stop.clear()
    _replay_thread = threading.Thread(target=_replay_loop, name="kb-extract-replay", daemon=True)
    _replay_thread.start()


def stop_periodic_replay() -> None:
    _replay_stop.set()
    if _replay_thread:
        _replay_thread.join(timeout=5)


def run_consumer() -> None:
    from config import KB_EXTRACT_CONCURRENCY

    prefetch = max(1, int(KB_EXTRACT_CONCURRENCY))
    start_periodic_replay()
    while True:
        connection: pika.BlockingConnection | None = None
        try:
            connection = open_blocking_connection()
            channel = connection.channel()
            declare_kb_extract_topology(channel)
            channel.basic_qos(prefetch_count=prefetch)
            channel.basic_consume(
                queue=QUEUE_MAIN,
                on_message_callback=_on_message,
                auto_ack=False,
            )
            logger.info("kb-extract consumer listening on %s (prefetch=%s)", QUEUE_MAIN, prefetch)
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
            logger.warning("kb-extract connection lost (%s); reconnecting", exc)
            time.sleep(KB_EXTRACT_CONSUMER_RECONNECT_SEC)
        except Exception:
            logger.exception("kb-extract consumer error; reconnecting")
            time.sleep(KB_EXTRACT_CONSUMER_RECONNECT_SEC)
        finally:
            if connection is not None:
                try:
                    if connection.is_open:
                        connection.close()
                except Exception:
                    pass
