# Copyright (c) 2026 徐泽宇
"""RabbitMQ consumer for KB index jobs (prefetch controlled by KB_INDEX_CONCURRENCY).

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

from config import KB_INDEX_REPLAY_STALE_SEC
from database import SessionLocal
from services.license_service import require_license_or_wait
from messaging.kb_index_publisher import (
    publish_file_index_notify,
    publish_kb_index_dlq,
    publish_kb_index_retry,
)
from messaging.kb_index_queues import (
    QUEUE_MAIN,
    declare_kb_index_topology,
    open_blocking_connection,
)
from models.file import File as FileModel
from models.kb_index_job import KbIndexJob
from models.kb_correction_overlay import KbCorrectionOverlay
from services.kb_index_service import (
    _LeaseToken,
    JOB_DONE,
    JOB_ERROR,
    JOB_QUEUED,
    JOB_RUNNING,
    KB_INDEX_DEADLOCK_BACKOFF_BASE_SEC,
    KB_INDEX_DEADLOCK_MAX_RETRIES,
    STATUS_FAILED,
    claim_kb_index_job,
    is_pg_deadlock,
    make_kb_index_worker_id,
    reconcile_stale_kb_index_jobs,
    reconcile_superseded_running_jobs,
    run_index_job,
)
from services.system_setting_service import get_kb_index_max_attempts
from services.user_setting_service import get_user_effective_dict
from utils.timezone import beijing_now, naive_db_now

logger = logging.getLogger(__name__)


def _log_time_beijing() -> str:
    return beijing_now().strftime("%Y-%m-%d %H:%M:%S")


KB_INDEX_CONSUMER_RECONNECT_SEC = 3

_replay_stop = threading.Event()
_replay_thread: threading.Thread | None = None

# 并发闸：限制同时持有 DB 连接的索引后台线程数，防止突发批量 index 任务
# 打满 SQLAlchemy QueuePool（消费者收到消息后立即 ack 再派发 daemon 线程，
# prefetch 无法限流；此处用信号量把真正占用 DB session 的并发收敛到
# KB_INDEX_CONCURRENCY，从而保证 pool 不会被突发撑爆）。
_index_concurrency_sem: threading.BoundedSemaphore | None = None


def _index_semaphore() -> threading.BoundedSemaphore:
    global _index_concurrency_sem
    if _index_concurrency_sem is None:
        from config import KB_INDEX_CONCURRENCY
        _index_concurrency_sem = threading.BoundedSemaphore(max(1, int(KB_INDEX_CONCURRENCY)))
    return _index_concurrency_sem


def replay_queued_jobs(db: Session, *, full: bool = False) -> int:
    """将 DB 中 queued 任务补发到 RabbitMQ。

    full=True：启动时一次性补发全部 queued（恢复宕机期间丢失的消息）。
    full=False：仅补发「陈旧」queued（updated_at 早于阈值），避免周期性全量重发撑爆队列。
    """
    from messaging.kb_index_publisher import publish_kb_index_job

    q = db.query(KbIndexJob).filter(KbIndexJob.status == JOB_QUEUED)
    if not full:
        cutoff = naive_db_now() - timedelta(seconds=KB_INDEX_REPLAY_STALE_SEC)
        q = q.filter(KbIndexJob.updated_at <= cutoff)
    jobs = q.order_by(KbIndexJob.id).all()
    if not jobs:
        return 0
    conn = open_blocking_connection()
    now = naive_db_now()
    try:
        for job in jobs:
            publish_kb_index_job(job.id, connection=conn)
            job.updated_at = now
    finally:
        conn.close()
    db.commit()
    logger.info(
        "replayed %s queued kb index job(s) to RabbitMQ (full=%s)",
        len(jobs),
        full,
    )
    return len(jobs)


def _publish_index_notify_safe(
    f: FileModel,
    conn: pika.BlockingConnection | None,
    *,
    processing_duration_ms: int | None = None,
) -> None:
    try:
        publish_file_index_notify(
            f,
            connection=conn,
            processing_duration_ms=processing_duration_ms,
        )
    except Exception:
        logger.exception("publish index notify failed file_id=%s", f.id)


def _handle_job(db: Session, job_id: int, conn: pika.BlockingConnection | None = None) -> _LeaseToken | None:
    job = claim_kb_index_job(db, job_id, worker_id=make_kb_index_worker_id())
    token = _LeaseToken(worker_id=job.worker_id, lease_generation=job.lease_generation) if job else None
    if not job:
        stale = db.query(KbIndexJob).filter(KbIndexJob.id == job_id).first()
        if stale:
            logger.warning(
                "kb index message for job_id=%s ignored (status=%s, not queued)",
                job_id,
                stale.status,
            )
        else:
            logger.warning("kb index message for unknown job_id=%s", job_id)
        return

    owner = db.query(FileModel).filter(FileModel.id == job.file_id).first()
    effective = get_user_effective_dict(db, owner.user_id) if owner else None
    max_attempts = get_kb_index_max_attempts(
        db,
        user_id=owner.user_id if owner else None,
        effective=effective,
    )
    if reconcile_superseded_running_jobs(db, job.file_id, job.id):
        db.commit()
    start_perf = time.perf_counter()
    for deadlock_attempt in range(KB_INDEX_DEADLOCK_MAX_RETRIES):
        try:
            run_index_job(
                db,
                job,
                effective=effective,
                resume_after_deadlock=deadlock_attempt > 0,
            )
            reconcile_superseded_running_jobs(db, job.file_id, job.id)
            if job.correction_overlay_id and job.status == JOB_ERROR:
                # run_index_job stages chunk/vector changes in this transaction.  A
                # correction failure must roll that transaction back so the prior
                # index remains readable; then persist only the terminal job state.
                failed_job_id = int(job.id)
                failure = (job.last_error or "correction overlay reindex failed")[:2000]
                db.rollback()
                job = db.query(KbIndexJob).filter(KbIndexJob.id == failed_job_id).one()
                overlay = db.query(KbCorrectionOverlay).filter(
                    KbCorrectionOverlay.id == job.correction_overlay_id
                ).one_or_none()
                job.status = JOB_ERROR
                job.last_error = failure
                if overlay is not None:
                    overlay.reindex_status = "FAILED"
                db.commit()
            else:
                db.commit()
            break
        except OperationalError as exc:
            if not is_pg_deadlock(exc):
                raise
            if deadlock_attempt >= KB_INDEX_DEADLOCK_MAX_RETRIES - 1:
                msg = str(exc)[:2000]
                recover_job_id = job.id
                db.rollback()
                _recover_handler_error(recover_job_id, msg, conn=conn, token=token)
                return
            job_id = job.id
            db.rollback()
            job = db.query(KbIndexJob).filter(KbIndexJob.id == job_id).one()
            logger.warning(
                "kb_index_deadlock_retry job_id=%s file_id=%s attempt=%s/%s",
                job.id,
                job.file_id,
                deadlock_attempt + 1,
                KB_INDEX_DEADLOCK_MAX_RETRIES,
            )
            time.sleep(KB_INDEX_DEADLOCK_BACKOFF_BASE_SEC * (2 ** (deadlock_attempt + 1)))
    processing_duration_ms = int((time.perf_counter() - start_perf) * 1000)

    db.refresh(job)
    f = db.query(FileModel).filter(FileModel.id == job.file_id).first()

    if job.status == JOB_DONE:
        from models.kb_post_job import KbPostJob
        from services.kb_post_service import JOB_QUEUED as POST_QUEUED, publish_post_job, publish_file_post_notify_safe

        post_job = (
            db.query(KbPostJob)
            .filter(KbPostJob.index_job_id == job.id, KbPostJob.status == POST_QUEUED)
            .first()
        )
        if post_job:
            publish_post_job(db, job.user_id, job.file_id, post_job.id)
        elif f and (f.kb_post_status or "") not in {"", "pending", "queued", "running"}:
            try:
                publish_file_post_notify_safe(f)
            except Exception:
                logger.exception("publish kb post notify after sync index file_id=%s", f.id)
        if f:
            _publish_index_notify_safe(
                f,
                conn,
                processing_duration_ms=processing_duration_ms,
            )
        return

    if job.status != JOB_ERROR:
        if f:
            _publish_index_notify_safe(f, conn)
        return

    if (job.attempts or 0) < max_attempts:
        if f:
            _publish_index_notify_safe(f, conn)
        job.status = JOB_QUEUED
        if f:
            f.index_status = "pending"
            f.index_error = None
        db.commit()
        publish_kb_index_retry(job.id, connection=conn)
        if f:
            _publish_index_notify_safe(f, conn)
        logger.warning(
            "kb_index_job_retry_scheduled job_id=%s file_id=%s attempt=%s/%s last_error=%s",
            job.id,
            job.file_id,
            job.attempts,
            max_attempts,
            (job.last_error or "")[:500],
        )
        return

    publish_kb_index_dlq(job.id, last_error=job.last_error)
    if f:
        _publish_index_notify_safe(
            f,
            conn,
            processing_duration_ms=processing_duration_ms,
        )
    logger.error(
        "kb_index_job_dlq job_id=%s file_id=%s attempts=%s last_error=%s",
        job.id,
        job.file_id,
        job.attempts,
        (job.last_error or "")[:500],
    )
    return token


def _recover_handler_error(job_id: int, detail: str, conn: pika.BlockingConnection | None = None, token: _LeaseToken | None = None) -> None:
    """handler 异常时递增 attempts，未超限则 QUEUED + 重发，否则 ERROR + DLQ。"""
    db = SessionLocal()
    try:
        job = db.query(KbIndexJob).filter(KbIndexJob.id == job_id).first()
        if not job:
            return
        # Lease fencing: only the worker that claimed this job may modify it.
        # Without a token, never touch a job that another worker may own.
        if job.status == JOB_RUNNING:
            if token is None:
                logger.warning(
                    "kb_index_recover_skip_no_token job_id=%s status=running",
                    job_id,
                )
                return
            if job.worker_id != token.worker_id or job.lease_generation != token.lease_generation:
                logger.warning(
                    "kb_index_recover_lease_mismatch job_id=%s "
                    "token_worker=%s actual_worker=%s token_gen=%s actual_gen=%s",
                    job_id, token.worker_id, job.worker_id,
                    token.lease_generation, job.lease_generation,
                )
                return
        if job.status != JOB_RUNNING:
            return
        owner = db.query(FileModel).filter(FileModel.id == job.file_id).first()
        try:
            effective = get_user_effective_dict(db, owner.user_id) if owner else None
            max_attempts = get_kb_index_max_attempts(
                db,
                user_id=owner.user_id if owner else None,
                effective=effective,
            )
        except Exception:
            logger.exception(
                "kb_index_handler_retry_settings_failed job_id=%s file_id=%s; fallback max_attempts=3",
                job.id,
                job.file_id,
            )
            max_attempts = 3
        job.attempts = (job.attempts or 0) + 1
        msg = (detail or "kb index handler failed")[:2000]
        job.last_error = msg
        f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
        if (job.attempts or 0) < max_attempts:
            job.status = JOB_QUEUED
            if f:
                f.index_status = "pending"
                f.index_error = None
            db.commit()
            publish_kb_index_retry(job.id, connection=conn)
            if f:
                try:
                    publish_file_index_notify(f, connection=conn)
                except Exception:
                    logger.exception("publish handler retry notify failed file_id=%s", f.id)
            logger.warning(
                "kb_index_handler_retry job_id=%s file_id=%s attempt=%s/%s",
                job.id,
                job.file_id,
                job.attempts,
                max_attempts,
            )
            return
        job.status = JOB_ERROR
        if f:
            f.index_status = STATUS_FAILED
            f.index_error = msg
        db.commit()
        publish_kb_index_dlq(job.id, last_error=job.last_error)
        logger.error(
            "kb_index_handler_dlq job_id=%s file_id=%s attempts=%s",
            job.id,
            job.file_id,
            job.attempts,
        )
    except Exception:
        logger.exception("failed to recover kb index job %s after handler failure", job_id)
        db.rollback()
    finally:
        db.close()


def _on_message(ch, method, _properties, body: bytes) -> None:
    try:
        payload = json.loads(body.decode("utf-8"))
        job_id = int(payload["job_id"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("invalid kb index message body: %r", body[:200])
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    db = SessionLocal()
    start_time_str = _log_time_beijing()
    file_id: int | None = None
    try:
        job_row = db.query(KbIndexJob.file_id).filter(KbIndexJob.id == job_id).first()
        if job_row is not None:
            file_id = int(job_row[0])
        logger.info(
            "【索引消费者】接到索引任务：job_id=%s，file_id=%s，开始时间=%s",
            job_id,
            file_id if file_id is not None else "未知",
            start_time_str,
        )
        if not require_license_or_wait(db):
            logger.info("kb_index license invalid, requeue job_id=%s", job_id)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return
        # Ack immediately to release prefetch and allow pika heartbeats during long-running
        # index work (chunk+embed for large docs). The heavy lifting runs in a bg thread.
        ch.basic_ack(delivery_tag=method.delivery_tag)

        def _bg_handle(jid: int) -> None:
            sem = _index_semaphore()
            sem.acquire()
            db_bg = SessionLocal()
            token = None
            try:
                token = _handle_job(db_bg, jid, conn=None)
            except OperationalError:
                logger.exception("bg kb_index db unavailable job_id=%s (will rely on replay)", jid)
            except Exception as exc:
                logger.exception("bg kb_index handler error job_id=%s", jid)
                try:
                    _recover_handler_error(jid, str(exc)[:2000], conn=None, token=token)
                except Exception:
                    logger.exception("bg kb_index recover failed job_id=%s", jid)
            finally:
                db_bg.close()
                sem.release()

        threading.Thread(
            target=_bg_handle,
            args=(job_id,),
            daemon=True,
            name=f"kb-index-bg-{job_id}",
        ).start()
        # Emit the end log synchronously (dispatch time is near-zero); real phase timings
        # (embed_ms etc) are emitted by run_index_job via pipeline logs.
        end_time_str = _log_time_beijing()
        logger.info(
            "【索引消费者】索引任务结束：job_id=%s，file_id=%s，结束时间=%s，耗时=%.2f 秒（%.0f 毫秒），%s",
            job_id,
            file_id if file_id is not None else "未知",
            end_time_str,
            0.0,
            0,
            "已派发后台处理",
        )
        return
    except OperationalError:
        logger.exception("kb index job %s db unavailable at dispatch, message requeued", job_id)
        db.rollback()
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return
    except Exception as exc:
        logger.exception("kb index job %s pre-dispatch error", job_id)
        db.rollback()
        # best effort recover (may open fresh conn)
        try:
            _recover_handler_error(job_id, str(exc), conn=None)
        except Exception:
            pass
        # ack to not leave redeliver storm
        try:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            pass
    finally:
        db.close()


def _replay_loop() -> None:
    from config import KB_INDEX_REPLAY_INTERVAL_SEC

    while not _replay_stop.is_set():
        try:
            db = SessionLocal()
            try:
                if not require_license_or_wait(db):
                    continue
                stats = reconcile_stale_kb_index_jobs(db)
                if any(stats.values()):
                    db.commit()
                    logger.info("periodic reconciled stale kb index state: %s", stats)
                n = replay_queued_jobs(db, full=bool(stats.get("running_requeued")))
                if n:
                    logger.info("periodic stale replay republished %s queued job(s)", n)
            finally:
                db.close()
        except Exception:
            logger.exception("periodic kb index job replay failed")
        _replay_stop.wait(KB_INDEX_REPLAY_INTERVAL_SEC)


def start_periodic_replay() -> None:
    from config import KB_INDEX_REPLAY_INTERVAL_SEC

    if KB_INDEX_REPLAY_INTERVAL_SEC <= 0:
        logger.info("kb-index periodic replay disabled (KB_INDEX_REPLAY_INTERVAL_SEC<=0)")
        return
    global _replay_thread
    if _replay_thread and _replay_thread.is_alive():
        return
    _replay_stop.clear()
    _replay_thread = threading.Thread(target=_replay_loop, name="kb-index-replay", daemon=True)
    _replay_thread.start()


def stop_periodic_replay() -> None:
    _replay_stop.set()
    if _replay_thread:
        _replay_thread.join(timeout=5)


def run_consumer() -> None:
    """阻塞运行主队列消费者；RabbitMQ 重启或断连时自动重连（不退出进程）。"""
    start_periodic_replay()
    while True:
        connection: pika.BlockingConnection | None = None
        try:
            connection = open_blocking_connection()
            channel = connection.channel()
            declare_kb_index_topology(channel)
            from config import KB_INDEX_CONCURRENCY
            prefetch = max(1, int(KB_INDEX_CONCURRENCY))
            channel.basic_qos(prefetch_count=prefetch)
            channel.basic_consume(
                queue=QUEUE_MAIN,
                on_message_callback=_on_message,
                auto_ack=False,
            )
            logger.info("kb-index consumer listening on %s (prefetch=%s)", QUEUE_MAIN, prefetch)
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
            logger.warning(
                "kb-index consumer connection lost (%s); reconnecting in %ss",
                exc,
                KB_INDEX_CONSUMER_RECONNECT_SEC,
            )
            time.sleep(KB_INDEX_CONSUMER_RECONNECT_SEC)
        except Exception:
            logger.exception(
                "kb-index consumer error; reconnecting in %ss",
                KB_INDEX_CONSUMER_RECONNECT_SEC,
            )
            time.sleep(KB_INDEX_CONSUMER_RECONNECT_SEC)
        finally:
            if connection is not None:
                try:
                    if connection.is_open:
                        connection.close()
                except Exception:
                    pass
