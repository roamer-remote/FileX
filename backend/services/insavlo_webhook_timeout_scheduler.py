# Copyright (c) 2026 徐泽宇
"""Insavlo webhook timeout scanner (044 FR-F / stage 5; 063 minutes).

A lifespan background coroutine on the ``filex`` API process periodically scans
``waiting_webhook`` Insavlo jobs whose ``remote_submitted_at + timeout_minutes``
(in minutes) has elapsed (falling back to ``updated_at``). Timed-out jobs are
marked failed **without** legacy fallback; a WebSocket notification is emitted.

Multi-instance mutual exclusion uses a dedicated advisory lock (``900044``),
distinct from wiki lint (``900009``) and the write-back loop (``910044``).
Logs record only transaction/job/file identifiers — never secrets or auth.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from models.file import File as FileModel
from models.kb_extract_job import KbExtractJob
from services.kb_extract_service import (
    JOB_ERROR,
    JOB_WAITING_WEBHOOK,
    STATUS_FAILED,
)
from services.kb_pipeline_log_service import (
    ACTION_INSAVLO_WEBHOOK_TIMEOUT,
    ACTION_KB_EXTRACT_ERROR,
    format_kb_pipeline_detail,
    log_kb_pipeline_event,
    pipeline_reason,
)
from services.system_setting_service import (
    KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
    get_public_settings_dict,
)
from utils.timezone import naive_db_now

logger = logging.getLogger(__name__)

INSAVLO_WEBHOOK_TIMEOUT_LOCK_KEY = 900044  # 044 FR-F advisory lock; 063 unchanged (minutes only)
# Upper bound for scan cadence (env override). Short timeouts use a smaller adaptive interval.
INSAVLO_WEBHOOK_TIMEOUT_SCAN_INTERVAL_SEC_MAX = max(
    60, int(os.environ.get("INSAVLO_WEBHOOK_TIMEOUT_SCAN_INTERVAL_SEC") or "900")
)
INSAVLO_WEBHOOK_TIMEOUT_SCAN_INTERVAL_SEC_MIN = max(
    5, int(os.environ.get("INSAVLO_WEBHOOK_TIMEOUT_SCAN_INTERVAL_SEC_MIN") or "10")
)
INSAVLO_WEBHOOK_TIMEOUT_ERROR = "insavlo webhook timeout"
INSAVLO_WEBHOOK_TIMEOUT_DEFAULT_MINUTES = 120


def compute_webhook_timeout_scan_interval_sec(timeout_minutes: int) -> float:
    """Pick scan cadence so short webhook timeouts are detected promptly.

    Effective user-visible timeout ≈ ``timeout_minutes`` + up to one scan interval.
    """
    try:
        minutes = int(timeout_minutes)
    except (TypeError, ValueError):
        minutes = INSAVLO_WEBHOOK_TIMEOUT_DEFAULT_MINUTES
    minutes = max(1, minutes)
    adaptive = max(INSAVLO_WEBHOOK_TIMEOUT_SCAN_INTERVAL_SEC_MIN, minutes * 15)
    return float(min(adaptive, INSAVLO_WEBHOOK_TIMEOUT_SCAN_INTERVAL_SEC_MAX))


def _get_timeout_minutes(db: Session) -> int:
    from services.system_setting_service import _parse_kb_extract_insavlo_timeout_minutes

    try:
        settings = get_public_settings_dict(db)
        raw = settings.get(
            KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
            str(INSAVLO_WEBHOOK_TIMEOUT_DEFAULT_MINUTES),
        )
        return _parse_kb_extract_insavlo_timeout_minutes(str(raw))
    except (ValueError, TypeError):
        return INSAVLO_WEBHOOK_TIMEOUT_DEFAULT_MINUTES


def _notify_file(f: FileModel) -> None:
    from messaging.kb_extract_publisher import publish_file_extract_notify

    try:
        publish_file_extract_notify(f)
    except Exception:
        logger.exception("publish insavlo timeout notify failed file_id=%s", f.id)


def scan_insavlo_webhook_timeouts(db: Session) -> int:
    """Mark timed-out ``waiting_webhook`` Insavlo jobs as failed. Returns count.

    Safe to call directly (tests) or from the lifespan loop. Acquires a
    dedicated advisory lock so only one instance scans at a time.
    """
    got = db.execute(
        text("SELECT pg_try_advisory_lock(:k)"), {"k": INSAVLO_WEBHOOK_TIMEOUT_LOCK_KEY}
    ).scalar()
    if not got:
        return 0
    try:
        minutes = _get_timeout_minutes(db)
        cutoff = naive_db_now() - timedelta(minutes=minutes)
        jobs = (
            db.query(KbExtractJob)
            .filter(
                KbExtractJob.status == JOB_WAITING_WEBHOOK,
                KbExtractJob.provider == "insavlo",
            )
            .with_for_update(skip_locked=True)
            .all()
        )
        timed_out: list[tuple[KbExtractJob, FileModel | None]] = []
        for job in jobs:
            submitted = job.remote_submitted_at or job.updated_at
            if submitted is None:
                continue
            if submitted > cutoff:
                continue
            f = db.query(FileModel).filter(FileModel.id == job.file_id).first()
            job.status = JOB_ERROR
            job.last_error = INSAVLO_WEBHOOK_TIMEOUT_ERROR
            if f is not None:
                f.extract_status = STATUS_FAILED
                f.extract_error = INSAVLO_WEBHOOK_TIMEOUT_ERROR
            log_kb_pipeline_event(
                db,
                job.user_id,
                ACTION_INSAVLO_WEBHOOK_TIMEOUT,
                job.file_id,
                detail=format_kb_pipeline_detail(
                    job_id=job.id,
                    provider=job.provider,
                    reason=pipeline_reason(INSAVLO_WEBHOOK_TIMEOUT_ERROR),
                    timeout_minutes=minutes,
                    transaction_id=job.remote_transaction_id,
                ),
            )
            log_kb_pipeline_event(
                db,
                job.user_id,
                ACTION_KB_EXTRACT_ERROR,
                job.file_id,
                detail=format_kb_pipeline_detail(
                    job_id=job.id,
                    provider=job.provider,
                    reason=pipeline_reason(INSAVLO_WEBHOOK_TIMEOUT_ERROR),
                ),
            )
            timed_out.append((job, f))
            logger.warning(
                "insavlo webhook timeout job_id=%s file_id=%s transaction_id=%s timeout_minutes=%s",
                job.id,
                job.file_id,
                job.remote_transaction_id,
                minutes,
            )
        if timed_out:
            db.commit()
        for _job, f in timed_out:
            if f is not None:
                _notify_file(f)
        return len(timed_out)
    except Exception:
        db.rollback()
        logger.exception("insavlo webhook timeout scan failed")
        return 0
    finally:
        db.execute(
            text("SELECT pg_advisory_unlock(:k)"), {"k": INSAVLO_WEBHOOK_TIMEOUT_LOCK_KEY}
        )


def _run_timeout_scan() -> int:
    db = SessionLocal()
    try:
        return scan_insavlo_webhook_timeouts(db)
    finally:
        db.close()


def _compute_scan_sleep_sec() -> float:
    db = SessionLocal()
    try:
        return compute_webhook_timeout_scan_interval_sec(_get_timeout_minutes(db))
    finally:
        db.close()


async def insavlo_webhook_timeout_loop() -> None:
    """Lifespan loop: scan for timed-out Insavlo webhook jobs on an adaptive interval."""
    while True:
        try:
            await asyncio.to_thread(_run_timeout_scan)
        except Exception:
            logger.exception("insavlo webhook timeout scheduler loop error")
        sleep_sec = await asyncio.to_thread(_compute_scan_sleep_sec)
        await asyncio.sleep(sleep_sec)
