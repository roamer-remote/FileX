# Copyright (c) 2026 徐泽宇
"""RabbitMQ consumer for KB post jobs (114)."""

from __future__ import annotations

import json
import logging
import threading
import time

import pika
import pika.exceptions as pika_exc
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from database import SessionLocal
from messaging.kb_post_publisher import publish_kb_post_dlq, publish_kb_post_retry
from messaging.kb_post_queues import QUEUE_MAIN, declare_kb_post_topology, open_blocking_connection
from models.file import File as FileModel
from models.kb_post_job import KbPostJob
from services.kb_post_service import (
    _LeaseToken,
    JOB_DONE,
    JOB_ERROR,
    JOB_QUEUED,
    JOB_RUNNING,
    JOB_WAITING_GPU,
    POST_STATUS_FAILED,
    POST_STATUS_QUEUED,
    KbPostJobAborted,
    claim_kb_post_job,
    make_kb_post_worker_id,
    publish_file_post_notify_safe,
    reconcile_stale_kb_post_jobs,
    replay_queued_post_jobs,
    run_post_job,
)
from services.license_service import require_license_or_wait
from services.system_setting_service import get_kb_post_max_attempts
from services.user_setting_service import get_user_effective_dict
from utils.timezone import beijing_now

logger = logging.getLogger(__name__)

KB_POST_CONSUMER_RECONNECT_SEC = 3

_replay_stop = threading.Event()
_replay_thread: threading.Thread | None = None

# 并发闸：限制同时持有 DB 连接的后处理后台线程数，防止突发批量 post 任务
# 打满 SQLAlchemy QueuePool（消费者收到消息后立即 ack 再派发 daemon 线程，
# prefetch 无法限流；此处用信号量把真正占用 DB session 的并发收敛到
# KB_POST_CONCURRENCY，从而保证 pool 不会被突发撑爆）。
_post_concurrency_sem: threading.BoundedSemaphore | None = None


def _post_semaphore() -> threading.BoundedSemaphore:
    global _post_concurrency_sem
    if _post_concurrency_sem is None:
        from config import KB_POST_CONCURRENCY
        _post_concurrency_sem = threading.BoundedSemaphore(max(1, int(KB_POST_CONCURRENCY)))
    return _post_concurrency_sem


def _log_time_beijing() -> str:
    return beijing_now().strftime("%Y-%m-%d %H:%M:%S")


def _publish_post_notify_safe(
    f: FileModel,
    job: KbPostJob,
    *,
    processing_duration_ms: int | None = None,
) -> None:
    try:
        publish_file_post_notify_safe(
            f,
            processing_duration_ms=processing_duration_ms,
            post_entity_ms=job.post_entity_ms,
            post_sag_ms=job.post_sag_ms,
            post_raptor_ms=job.post_raptor_ms,
            post_skip_reason=job.post_skip_reason,
        )
    except Exception:
        logger.exception("publish kb post notify failed file_id=%s", f.id)


def _handle_job(
    db: Session,
    job_id: int,
    conn: pika.BlockingConnection | None = None,
    *,
    _from_gpu_scheduler: bool = False,
) -> tuple[_LeaseToken | None, int | None]:
    """执行一个 post job；返回 ``(token, claimed_route_id)``。

    ``claimed_route_id`` 为本轮 claim 成功的 GPU route id（未 claim 为 None），
    GPU scheduler 消费端据此区分「本轮 defer」与「其他执行轮仍持有」。
    """
    from services.gpu_scheduler_persistence import (
        ack_gpu_route,
        claim_gpu_execution,
        find_gpu_route,
        reopen_gpu_route,
        release_gpu_execution,
        release_gpu_lease_for_job,
    )

    gpu_route = find_gpu_route(db, job_kind="raptor", job_id=job_id)
    from config import GPU_SCHEDULER_ENABLED, GPU_SCHEDULER_OWNER_ID

    if (
        GPU_SCHEDULER_ENABLED
        and gpu_route is None
        and not _from_gpu_scheduler
        and _post_job_uses_gpu(db, job_id)
    ):
        # 164 §6：GPU 模式下 raptor 候选 job 缺失 durable route（迁移期遗留行
        # 或 enqueue 后设置变化）时回查补建，绝不无租约执行 RAPTOR。
        from services.gpu_scheduler_persistence import enqueue_gpu_route

        job_row = db.query(KbPostJob).filter(KbPostJob.id == job_id).first()
        if job_row is not None:
            enqueue_gpu_route(
                db,
                job_kind="raptor",
                job_id=job_id,
                file_id=job_row.file_id,
                idempotency_key=f"raptor:{job_id}:0",
                payload={
                    "job_id": int(job_id),
                    "job_kind": "raptor",
                    "file_id": int(job_row.file_id),
                    "attempt": 0,
                    "idempotency_key": f"raptor:{job_id}:0",
                    "handover_epoch": 0,
                },
            )
            db.commit()
            logger.info("kb post backfilled raptor route for gpu scheduler job_id=%s", job_id)
            return None, None

    if GPU_SCHEDULER_ENABLED and gpu_route is not None and not _from_gpu_scheduler:
        # 164 §6：GPU 调度模式下旧 post consumer 只提交 GPU job 后立即 ack，
        # 不执行 GPU。published route 只在无活跃 dispatch lease（遗留桥接）
        # 时退回 queued；scheduler 已取得租约的 route 由 scheduler consumer
        # 处理，旧 consumer 不得重开或释放 lease（164 §6 / P3）。
        if gpu_route.state == "published":
            from services.gpu_scheduler_persistence import (
                find_active_lease_for_job,
            )

            active_lease = find_active_lease_for_job(
                db,
                job_id=job_id,
                owner_id=GPU_SCHEDULER_OWNER_ID,
            )
            if active_lease is None:
                reopened = reopen_gpu_route(db, outbox_id=gpu_route.id)
                if reopened is not None:
                    release_gpu_lease_for_job(
                        db,
                        job_id=job_id,
                        owner_id=GPU_SCHEDULER_OWNER_ID,
                    )
            else:
                logger.info(
                    "kb post skip handover reopen: scheduler lease active job_id=%s",
                    job_id,
                )
        db.commit()
        logger.info("kb post handed over to gpu scheduler job_id=%s", job_id)
        return None, None


    gpu_route_id = None
    if gpu_route is not None:
        claimed_route = claim_gpu_execution(db, job_kind="raptor", job_id=job_id)
        if claimed_route is None:
            logger.info("kb post duplicate or unpublished GPU route ignored job_id=%s", job_id)
            db.rollback()
            return None, None
        gpu_route_id = claimed_route.id

    job = claim_kb_post_job(db, job_id, worker_id=make_kb_post_worker_id())
    token = _LeaseToken(worker_id=job.worker_id, lease_generation=job.lease_generation) if job else None
    if not job:
        stale = db.query(KbPostJob).filter(KbPostJob.id == job_id).first()
        if stale:
            logger.warning(
                "kb post message for job_id=%s ignored (status=%s, not queued)",
                job_id,
                stale.status,
            )
        else:
            logger.warning("kb post message for unknown job_id=%s", job_id)
        if gpu_route_id is not None:
            release_gpu_execution(db, outbox_id=gpu_route_id)
            db.commit()
        return token, gpu_route_id

    owner = db.query(FileModel).filter(FileModel.id == job.file_id).first()
    effective = get_user_effective_dict(db, owner.user_id) if owner else None
    max_attempts = get_kb_post_max_attempts(
        db,
        user_id=owner.user_id if owner else None,
        effective=effective,
    )
    start_perf = time.perf_counter()
    try:
        run_post_job(db, job, effective=effective, _from_gpu_scheduler=_from_gpu_scheduler)
    except KbPostJobAborted:
        logger.info("kb_post job aborted job_id=%s file_id=%s", job.id, job.file_id)
        db.rollback()
        job = db.query(KbPostJob).filter(KbPostJob.id == job_id).first()
        if job is not None:
            f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
            if f is not None:
                try:
                    publish_file_post_notify_safe(f)
                except Exception:
                    logger.exception("publish kb post notify after abort file_id=%s", f.id)
        return None, gpu_route_id
    processing_duration_ms = int((time.perf_counter() - start_perf) * 1000)
    db.commit()

    db.refresh(job)
    f = db.query(FileModel).filter(FileModel.id == job.file_id).first()

    if job.status == JOB_DONE:
        if gpu_route_id is not None:
            ack_gpu_route(db, outbox_id=gpu_route_id)
            db.commit()
        if f:
            _publish_post_notify_safe(f, job, processing_duration_ms=processing_duration_ms)
        return token, gpu_route_id

    if job.status == JOB_WAITING_GPU:
        if gpu_route_id is not None:
            release_gpu_execution(db, outbox_id=gpu_route_id)
            db.commit()
        if f:
            _publish_post_notify_safe(f, job, processing_duration_ms=processing_duration_ms)
        logger.info("kb post job remains waiting for GPU job_id=%s file_id=%s", job.id, job.file_id)
        return token, gpu_route_id
    if job.status != JOB_ERROR:
        if gpu_route_id is not None:
            release_gpu_execution(db, outbox_id=gpu_route_id)
            db.commit()
        if f:
            _publish_post_notify_safe(f, job)
        return token, gpu_route_id

    if (job.attempts or 0) < max_attempts:
        if gpu_route_id is not None:
            release_gpu_execution(db, outbox_id=gpu_route_id)
            if _from_gpu_scheduler:
                # GPU 调度模式下 retry 由 dispatch loop 重新发布：route 立即
                # 退回 queued 并递增 handover_epoch，避免依赖旧 consumer 交接。
                reopen_gpu_route(db, outbox_id=gpu_route_id)
        job.status = JOB_QUEUED
        if f:
            f.kb_post_status = POST_STATUS_QUEUED
            f.kb_post_error = None
        db.commit()
        publish_kb_post_retry(job.id, connection=conn)
        if f:
            _publish_post_notify_safe(f, job)
        logger.warning(
            "kb_post_job_retry_scheduled job_id=%s file_id=%s attempt=%s/%s last_error=%s",
            job.id,
            job.file_id,
            job.attempts,
            max_attempts,
            (job.last_error or "")[:500],
        )
        return token, gpu_route_id

    publish_kb_post_dlq(job.id, last_error=job.last_error)
    if gpu_route_id is not None:
        ack_gpu_route(db, outbox_id=gpu_route_id)
    if f:
        f.kb_post_status = POST_STATUS_FAILED
        _publish_post_notify_safe(f, job, processing_duration_ms=processing_duration_ms)
    logger.error(
        "kb_post_job_dlq job_id=%s file_id=%s attempts=%s last_error=%s",
        job.id,
        job.file_id,
        job.attempts,
        (job.last_error or "")[:500],
    )
    return token, gpu_route_id


def _post_job_uses_gpu(db: Session, job_id: int) -> bool:
    """Post job 运行时是否可能执行 RAPTOR（raptor_only 或按文本长度/设置解析）。"""
    job = db.query(KbPostJob).filter(KbPostJob.id == job_id).first()
    if job is None:
        return False
    if getattr(job, "raptor_only", False):
        return True
    f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
    if f is None:
        return False
    from services.kb_text_source import resolve_index_text

    text, _source = resolve_index_text(f)
    if not text:
        return False
    from services.kb_post_service import _post_work_needed

    _needed, _skip, raptor_needed = _post_work_needed(
        db,
        md_char_count=len(text),
        large_pdf=False,
    )
    return raptor_needed


def _recover_handler_error(job_id: int, detail: str, conn: pika.BlockingConnection | None = None, token: _LeaseToken | None = None) -> None:
    db = SessionLocal()
    try:
        from services.gpu_scheduler_persistence import find_gpu_route, release_gpu_execution

        job = db.query(KbPostJob).filter(KbPostJob.id == job_id).first()
        if not job:
            return
        # Lease fencing: only the worker that claimed this job may modify it.
        if job.status == JOB_RUNNING:
            if token is None:
                logger.warning(
                    "kb_post_recover_skip_no_token job_id=%s status=running",
                    job_id,
                )
                return
            if job.worker_id != token.worker_id or job.lease_generation != token.lease_generation:
                logger.warning(
                    "kb_post_recover_lease_mismatch job_id=%s "
                    "token_worker=%s actual_worker=%s token_gen=%s actual_gen=%s",
                    job_id, token.worker_id, job.worker_id,
                    token.lease_generation, job.lease_generation,
                )
                return
        if job.status != JOB_RUNNING:
            return
        route = find_gpu_route(db, job_kind="raptor", job_id=job_id)
        if route is not None:
            release_gpu_execution(db, outbox_id=route.id)
        owner = db.query(FileModel).filter(FileModel.id == job.file_id).first()
        try:
            effective = get_user_effective_dict(db, owner.user_id) if owner else None
            max_attempts = get_kb_post_max_attempts(
                db,
                user_id=owner.user_id if owner else None,
                effective=effective,
            )
        except Exception:
            logger.exception(
                "kb_post_handler_retry_settings_failed job_id=%s file_id=%s; fallback max_attempts=3",
                job.id,
                job.file_id,
            )
            max_attempts = 3
        job.attempts = (job.attempts or 0) + 1
        msg = (detail or "kb post handler failed")[:2000]
        job.last_error = msg
        f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
        if (job.attempts or 0) < max_attempts:
            job.status = JOB_QUEUED
            if f:
                f.kb_post_status = POST_STATUS_QUEUED
                f.kb_post_error = None
            db.commit()
            publish_kb_post_retry(job.id, connection=conn)
            if f:
                _publish_post_notify_safe(f, job)
            logger.warning(
                "kb_post_handler_retry job_id=%s file_id=%s attempt=%s/%s",
                job.id,
                job.file_id,
                job.attempts,
                max_attempts,
            )
            return
        job.status = JOB_ERROR
        if f:
            f.kb_post_status = POST_STATUS_FAILED
            f.kb_post_error = msg
        db.commit()
        publish_kb_post_dlq(job.id, last_error=job.last_error)
        logger.error(
            "kb_post_handler_dlq job_id=%s file_id=%s attempts=%s",
            job.id,
            job.file_id,
            job.attempts,
        )
    except Exception:
        logger.exception("failed to recover kb post job %s after handler failure", job_id)
        db.rollback()
    finally:
        db.close()


def _on_message(ch, method, _properties, body: bytes) -> None:
    try:
        payload = json.loads(body.decode("utf-8"))
        job_id = int(payload["job_id"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.warning("invalid kb post message body: %r", body[:200])
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    db = SessionLocal()
    start_time_str = _log_time_beijing()
    file_id: int | None = None
    try:
        job_row = db.query(KbPostJob.file_id).filter(KbPostJob.id == job_id).first()
        if job_row is not None:
            file_id = int(job_row[0])
        logger.info(
            "【后处理消费者】接到后处理任务：job_id=%s，file_id=%s，开始时间=%s",
            job_id,
            file_id if file_id is not None else "未知",
            start_time_str,
        )
        if not require_license_or_wait(db):
            logger.info("kb_post license invalid, requeue job_id=%s", job_id)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return
        ch.basic_ack(delivery_tag=method.delivery_tag)

        def _bg_handle(jid: int) -> None:
            sem = _post_semaphore()
            sem.acquire()
            db_bg = SessionLocal()
            token = None
            try:
                token, _claimed_route = _handle_job(db_bg, jid, conn=None)
            except OperationalError:
                logger.exception("bg kb_post db unavailable job_id=%s (will rely on replay)", jid)
            except Exception as exc:
                logger.exception("bg kb_post handler error job_id=%s", jid)
                try:
                    _recover_handler_error(jid, str(exc)[:2000], conn=None, token=token)
                except Exception:
                    logger.exception("bg kb_post recover failed job_id=%s", jid)
            finally:
                db_bg.close()
                sem.release()

        threading.Thread(
            target=_bg_handle,
            args=(job_id,),
            daemon=True,
            name=f"kb-post-bg-{job_id}",
        ).start()
        end_time_str = _log_time_beijing()
        logger.info(
            "【后处理消费者】后处理任务结束：job_id=%s，file_id=%s，结束时间=%s，%s",
            job_id,
            file_id if file_id is not None else "未知",
            end_time_str,
            "已派发后台处理",
        )
        return
    except OperationalError:
        logger.exception("kb post job %s db unavailable at dispatch, message requeued", job_id)
        db.rollback()
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        return
    except Exception as exc:
        logger.exception("kb post job %s pre-dispatch error", job_id)
        db.rollback()
        try:
            _recover_handler_error(job_id, str(exc), conn=None)
        except Exception:
            pass
        try:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            pass
    finally:
        db.close()


def _replay_loop() -> None:
    from config import KB_POST_REPLAY_INTERVAL_SEC

    while not _replay_stop.is_set():
        try:
            db = SessionLocal()
            try:
                if not require_license_or_wait(db):
                    continue
                stats = reconcile_stale_kb_post_jobs(db)
                if any(stats.values()):
                    db.commit()
                    logger.info("periodic reconciled stale kb post state: %s", stats)
                n = replay_queued_post_jobs(db, full=bool(stats.get("running_requeued")))
                if n:
                    logger.info("periodic stale replay republished %s queued post job(s)", n)
            finally:
                db.close()
        except Exception:
            logger.exception("periodic kb post job replay failed")
        _replay_stop.wait(KB_POST_REPLAY_INTERVAL_SEC)


def start_periodic_replay() -> None:
    from config import KB_POST_REPLAY_INTERVAL_SEC

    if KB_POST_REPLAY_INTERVAL_SEC <= 0:
        logger.info("kb-post periodic replay disabled (KB_POST_REPLAY_INTERVAL_SEC<=0)")
        return
    global _replay_thread
    if _replay_thread and _replay_thread.is_alive():
        return
    _replay_stop.clear()
    _replay_thread = threading.Thread(target=_replay_loop, name="kb-post-replay", daemon=True)
    _replay_thread.start()


def stop_periodic_replay() -> None:
    _replay_stop.set()
    if _replay_thread:
        _replay_thread.join(timeout=5)


def run_consumer() -> None:
    start_periodic_replay()
    while True:
        connection: pika.BlockingConnection | None = None
        try:
            connection = open_blocking_connection()
            channel = connection.channel()
            declare_kb_post_topology(channel)
            from config import KB_POST_CONCURRENCY

            prefetch = max(1, int(KB_POST_CONCURRENCY))
            channel.basic_qos(prefetch_count=prefetch)
            channel.basic_consume(
                queue=QUEUE_MAIN,
                on_message_callback=_on_message,
                auto_ack=False,
            )
            logger.info("kb-post consumer listening on %s (prefetch=%s)", QUEUE_MAIN, prefetch)
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
                "kb-post consumer connection lost (%s); reconnecting in %ss",
                exc,
                KB_POST_CONSUMER_RECONNECT_SEC,
            )
            time.sleep(KB_POST_CONSUMER_RECONNECT_SEC)
        except Exception:
            logger.exception(
                "kb-post consumer error; reconnecting in %ss",
                KB_POST_CONSUMER_RECONNECT_SEC,
            )
            time.sleep(KB_POST_CONSUMER_RECONNECT_SEC)
        finally:
            if connection is not None:
                try:
                    if connection.is_open:
                        connection.close()
                except Exception:
                    pass
