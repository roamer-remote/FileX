# Copyright (c) 2026 徐泽宇
"""Insavlo webhook write-back: consume persisted events and render Markdown.

The webhook receiver persists ``insavlo_webhook_events`` and returns 200
(044 FR-D / SC-044-012). This module performs the *async* write-back on the
``filex`` API process: render Markdown -> persist note -> auto sync kb_index ->
enqueue vector index -> update job/file/event -> notify. It also provides the
lifespan loop and restart-recovery scan (SC-044-013).

Multi-instance mutual exclusion uses a dedicated PostgreSQL advisory lock; the
lock key is distinct from wiki lint (900009) and the Insavlo timeout scanner
(900044, stage 5). Row-level ``FOR UPDATE SKIP LOCKED`` is also applied when
selecting events to make the multi-consumer contract explicit.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from models.file import File as FileModel
from models.insavlo_webhook_event import InsavloWebhookEvent
from models.kb_extract_job import KbExtractJob
from services.insavlo_markdown_renderer import render_insavlo_markdown
from services.kb_extract_service import (
    JOB_DONE,
    JOB_ERROR,
    STATUS_FAILED,
    persist_extract_markdown,
)
from services.kb_pipeline_log_service import (
    ACTION_INSAVLO_WRITEBACK_DONE,
    ACTION_INSAVLO_WRITEBACK_ERROR,
    ACTION_KB_EXTRACT_DONE,
    format_kb_pipeline_detail,
    log_kb_pipeline_event,
    pipeline_reason,
)
from utils.timezone import naive_db_now

logger = logging.getLogger(__name__)

INSAVLO_WEBHOOK_WRITEBACK_LOCK_KEY = 910044
INSAVLO_WEBHOOK_WRITEBACK_POLL_SEC = 3.0
INSAVLO_WEBHOOK_MAX_ERROR_LEN = 2000

EVENT_PENDING = "pending"
EVENT_PROCESSING = "processing"
EVENT_DONE = "done"
EVENT_ERROR = "error"

_wake_event: asyncio.Event | None = None


def bind_insavlo_writeback_loop() -> None:
    """Bind the wake event to the running loop (called from lifespan)."""
    global _wake_event
    _wake_event = asyncio.Event()


def trigger_insavlo_writeback() -> None:
    """Wake the write-back loop to process just-persisted events (trigger only)."""
    if _wake_event is not None:
        _wake_event.set()


def _truncate(msg: str | None) -> str:
    return (msg or "")[:INSAVLO_WEBHOOK_MAX_ERROR_LEN]


def _notify_file(f: FileModel) -> None:
    from messaging.kb_extract_publisher import publish_file_extract_notify

    try:
        publish_file_extract_notify(f)
    except Exception:
        logger.exception("publish insavlo writeback notify failed file_id=%s", f.id)


def _log_insavlo_writeback(
    db: Session,
    *,
    user_id: int,
    file_id: int,
    action: str,
    **fields: object,
) -> None:
    detail = format_kb_pipeline_detail(**fields)
    log_kb_pipeline_event(db, user_id, action, file_id, detail=detail)


def _resolve_target_file(files: list[Any], job: KbExtractJob) -> dict[str, Any]:
    for item in files:
        if isinstance(item, dict) and item.get("file_id") == job.remote_file_id:
            return item
    for item in files:
        if isinstance(item, dict):
            return item
    return {}


def _determine_writeback_payload(payload: dict[str, Any], job: KbExtractJob) -> dict[str, Any]:
    """Return ``{"status": "ok"|"error", "result"?, "file_id"?, "skill_code"?, "msg"?}``."""
    transaction_status = str(payload.get("status") or "").lower()
    if transaction_status == "error":
        msg = payload.get("error") or payload.get("message") or "Insavlo transaction 处理失败"
        return {"status": "error", "msg": f"Insavlo transaction 失败: {msg}"}

    files = payload.get("files")
    if not isinstance(files, list) or not files:
        return {"status": "error", "msg": "Insavlo webhook payload 缺少 files"}

    target = _resolve_target_file(files, job)
    file_status = str(target.get("status") or "").lower()
    if file_status == "error":
        msg = target.get("msg") or target.get("error") or "Insavlo file 处理失败"
        return {"status": "error", "msg": f"Insavlo file 处理失败: {msg}"}

    result = target.get("result")
    all_error = all(
        isinstance(it, dict) and str(it.get("status") or "").lower() == "error" for it in files
    )
    if result in (None, "", {}) or all_error:
        return {"status": "error", "msg": "Insavlo 返回空 result 或全部文件处理失败"}

    return {
        "status": "ok",
        "result": result,
        "file_id": target.get("file_id"),
        "skill_code": target.get("skill_code"),
    }


def _fail_without_rollback(
    db: Session,
    event: InsavloWebhookEvent,
    job: KbExtractJob,
    f: FileModel,
    msg: str,
) -> None:
    """Mark event/job/file failed and commit (used when no partial mutation occurred)."""
    message = _truncate(msg)
    event.attempts = (event.attempts or 0) + 1
    event.status = EVENT_ERROR
    event.last_error = message
    event.processed_at = naive_db_now()
    f.extract_status = STATUS_FAILED
    f.extract_error = message
    job.status = JOB_ERROR
    job.last_error = message
    _log_insavlo_writeback(
        db,
        user_id=job.user_id,
        file_id=f.id,
        action=ACTION_INSAVLO_WRITEBACK_ERROR,
        event_id=event.id,
        job_id=job.id,
        transaction_id=event.transaction_id,
        reason=pipeline_reason(message),
    )
    db.commit()
    _notify_file(f)


def _writeback_event(db: Session, event: InsavloWebhookEvent) -> None:
    """Process one persisted event; commits on success or failure."""
    event_id = event.id
    transaction_id = event.transaction_id
    job = db.query(KbExtractJob).filter(KbExtractJob.id == event.job_id).first()
    f = db.query(FileModel).filter(FileModel.id == event.file_id).first()

    if job is None or f is None:
        user_id = job.user_id if job else (f.user_id if f else None)
        file_id = event.file_id or (job.file_id if job else (f.id if f else None))
        if user_id is not None and file_id is not None:
            _log_insavlo_writeback(
                db,
                user_id=user_id,
                file_id=file_id,
                action=ACTION_INSAVLO_WRITEBACK_ERROR,
                event_id=event_id,
                transaction_id=transaction_id,
                reason="orphan_event",
            )
        event.attempts = (event.attempts or 0) + 1
        event.status = EVENT_ERROR
        event.last_error = _truncate("Insavlo webhook 写回失败：关联 job/file 不存在")
        event.processed_at = naive_db_now()
        db.commit()
        return

    # Idempotency: a late/second write-back after the job already reached
    # done/error must not overwrite results or re-enqueue the index.
    if job.status == JOB_DONE:
        event.status = EVENT_DONE
        event.processed_at = naive_db_now()
        db.commit()
        return
    if job.status == JOB_ERROR:
        event.attempts = (event.attempts or 0) + 1
        event.status = EVENT_ERROR
        event.last_error = event.last_error or "job already error"
        event.processed_at = naive_db_now()
        db.commit()
        return

    job_id = job.id
    file_id = f.id

    payload = event.payload_json
    if not isinstance(payload, dict):
        try:
            payload = json.loads(payload or "{}")
        except (TypeError, ValueError):
            _fail_without_rollback(db, event, job, f, "Insavlo webhook payload 解析失败")
            return

    decision = _determine_writeback_payload(payload, job)
    if decision["status"] != "ok":
        _fail_without_rollback(
            db, event, job, f, decision.get("msg") or "Insavlo 写回失败"
        )
        return

    # Success path: mark processing, then render -> persist -> enqueue -> done.
    event.status = EVENT_PROCESSING
    event.attempts = (event.attempts or 0) + 1
    db.flush()
    try:
        result = decision["result"]
        markdown = render_insavlo_markdown(
            original_name=f.original_name or f.filename or "document",
            transaction_id=str(payload.get("transaction_id") or event.transaction_id),
            file_id=str(decision.get("file_id") or "") or None,
            skill_code=str(decision.get("skill_code") or job.remote_skill_code or "") or None,
            result=result if isinstance(result, dict) else {"value": result},
        )
        persist_extract_markdown(db, f, markdown, engine="insavlo", user_id=job.user_id)
        from services.knowledge_base_index_service import auto_sync_kb_index

        auto_sync_kb_index(db, f.user_id)
        job.status = JOB_DONE
        job.last_error = None
        job.remote_completed_at = naive_db_now()
        event.status = EVENT_DONE
        event.processed_at = naive_db_now()

        index_job_id: int | None = None
        if markdown.strip():
            from services.kb_index_service import enqueue_index_after_extract

            index_job_id = enqueue_index_after_extract(db, f, job)
            db.flush()
        index_enqueued = index_job_id is not None
        _log_insavlo_writeback(
            db,
            user_id=job.user_id,
            file_id=f.id,
            action=ACTION_INSAVLO_WRITEBACK_DONE,
            engine="insavlo",
            event_id=event.id,
            index_enqueued=index_enqueued,
            job_id=job.id,
            transaction_id=event.transaction_id,
        )
        _log_insavlo_writeback(
            db,
            user_id=job.user_id,
            file_id=f.id,
            action=ACTION_KB_EXTRACT_DONE,
            engine="insavlo",
            index_enqueued=index_enqueued,
            job_id=job.id,
            provider="insavlo",
        )
        if index_job_id is not None:
            db.commit()
            from services.kb_index_service import publish_index_job

            publish_index_job(db, f.user_id, f.id, index_job_id)
        else:
            db.commit()
        _notify_file(f)
    except Exception as exc:
        logger.exception("insavlo writeback failed event_id=%s job_id=%s", event_id, job_id)
        db.rollback()
        ev = db.query(InsavloWebhookEvent).filter(InsavloWebhookEvent.id == event_id).first()
        if ev is None or ev.status == EVENT_DONE:
            return
        j = db.query(KbExtractJob).filter(KbExtractJob.id == job_id).first()
        fl = db.query(FileModel).filter(FileModel.id == file_id).first()
        message = _truncate(str(exc))
        ev.attempts = (ev.attempts or 0) + 1
        ev.status = EVENT_ERROR
        ev.last_error = message
        ev.processed_at = naive_db_now()
        if fl is not None:
            fl.extract_status = STATUS_FAILED
            fl.extract_error = message
        if j is not None:
            j.status = JOB_ERROR
            j.last_error = message
        if j is not None and fl is not None:
            _log_insavlo_writeback(
                db,
                user_id=j.user_id,
                file_id=fl.id,
                action=ACTION_INSAVLO_WRITEBACK_ERROR,
                event_id=ev.id,
                job_id=j.id,
                transaction_id=ev.transaction_id,
                reason=pipeline_reason(message),
            )
        db.commit()
        if fl is not None:
            _notify_file(fl)


def process_insavlo_writeback_once(db: Session) -> int:
    """Process all pending/processing events serially under an advisory lock.

    Returns the number of events handled in this batch. Safe to call directly
    (tests, startup recovery) or from the lifespan loop.
    """
    got = db.execute(
        text("SELECT pg_try_advisory_lock(:k)"), {"k": INSAVLO_WEBHOOK_WRITEBACK_LOCK_KEY}
    ).scalar()
    if not got:
        return 0
    count = 0
    try:
        while True:
            event = (
                db.query(InsavloWebhookEvent)
                .filter(InsavloWebhookEvent.status.in_((EVENT_PENDING, EVENT_PROCESSING)))
                .order_by(InsavloWebhookEvent.id)
                .with_for_update(skip_locked=True)
                .first()
            )
            if event is None:
                break
            event_id = event.id
            try:
                _writeback_event(db, event)
            except Exception:
                db.rollback()
                logger.exception("insavlo writeback event handling failed event_id=%s", event_id)
            count += 1
        return count
    finally:
        db.execute(
            text("SELECT pg_advisory_unlock(:k)"), {"k": INSAVLO_WEBHOOK_WRITEBACK_LOCK_KEY}
        )


def _run_writeback_batch() -> int:
    db = SessionLocal()
    try:
        return process_insavlo_writeback_once(db)
    finally:
        db.close()


async def insavlo_webhook_writeback_loop() -> None:
    """Lifespan loop: periodically (or on wake) drain pending write-back events."""
    while True:
        processed = 0
        try:
            processed = await asyncio.to_thread(_run_writeback_batch)
        except Exception:
            logger.exception("insavlo writeback loop error")
        if processed:
            continue
        if _wake_event is not None:
            try:
                await asyncio.wait_for(
                    asyncio.shield(_wake_event.wait()),
                    timeout=INSAVLO_WEBHOOK_WRITEBACK_POLL_SEC,
                )
                _wake_event.clear()
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(INSAVLO_WEBHOOK_WRITEBACK_POLL_SEC)
