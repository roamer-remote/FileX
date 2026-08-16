# Copyright (c) 2026 徐泽宇
"""Consume the durable PostgreSQL RAGAS evaluation queue."""

from __future__ import annotations

import os
import signal
import socket
import time
from concurrent.futures import Future, ThreadPoolExecutor

import structlog
from sqlalchemy.orm import Session

from database import SessionLocal, init_db
from logging_setup import setup_logging
from services.kb_ragas_eval_queue_service import (
    claim_next_ragas_eval_job,
    reconcile_stale_ragas_eval_jobs,
    start_ragas_eval_attempt,
)
from services.system_setting_service import (
    DEFAULTS,
    KEY_KB_RAGAS_EVAL_CONCURRENCY,
    get_public_settings_dict,
)

setup_logging(service_name="kb-ragas-eval")
logger = structlog.get_logger("kb_ragas_eval")

DEFAULT_POLL_SECONDS = 1.0
RECONCILE_INTERVAL_SECONDS = 60.0


def get_ragas_eval_worker_settings(db: Session) -> tuple[int, float]:
    """Return the configured global claim limit and the worker poll interval."""
    settings = get_public_settings_dict(db)
    raw = settings.get(
        KEY_KB_RAGAS_EVAL_CONCURRENCY,
        DEFAULTS[KEY_KB_RAGAS_EVAL_CONCURRENCY],
    )
    try:
        concurrency = int(str(raw).strip())
    except (TypeError, ValueError):
        concurrency = int(DEFAULTS[KEY_KB_RAGAS_EVAL_CONCURRENCY])
    return max(1, min(4, concurrency)), DEFAULT_POLL_SECONDS


def execute_ragas_eval_job(db: Session, job: object) -> None:
    """Lazy import keeps worker orchestration testable without RAGAS imports."""
    from services.kb_eval_service import execute_ragas_eval_job as execute

    execute(db, job)


def process_one(db: Session, *, worker_id: str) -> bool:
    """Claim and process one job; the queue is the global concurrency authority."""
    concurrency, _ = get_ragas_eval_worker_settings(db)
    job = claim_next_ragas_eval_job(db, worker_id=worker_id, concurrency=concurrency)
    if job is None:
        return False
    # Commit releases the advisory transaction lock before the model call while
    # the valid running lease keeps the global limit in force.
    db.commit()
    if not start_ragas_eval_attempt(
        db,
        job_id=job.id,
        worker_id=worker_id,
        lease_generation=job.lease_generation,
    ):
        db.rollback()
        return False
    db.commit()
    execute_ragas_eval_job(db, job)
    return True


def _reconcile_once(db: Session) -> None:
    stats = reconcile_stale_ragas_eval_jobs(db)
    if any(stats.values()):
        logger.info("reconciled RAGAS jobs", **stats)
    db.commit()


def _process_one_in_session(worker_id: str) -> bool:
    db = SessionLocal()
    try:
        return process_one(db, worker_id=worker_id)
    except Exception:
        db.rollback()
        logger.exception("RAGAS worker job failed")
        return False
    finally:
        db.close()


def main() -> None:
    init_db(migrate=False)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    last_reconcile = 0.0
    stop_requested = False

    def _request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    from messaging.settings_invalidate_consumer import start_settings_invalidate_consumer

    start_settings_invalidate_consumer(service="kb-ragas-eval")
    logger.info("kb-ragas-eval started", worker_id=worker_id)
    futures: set[Future[bool]] = set()
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="kb-ragas-eval") as executor:
        while not stop_requested:
            db = SessionLocal()
            try:
                now = time.monotonic()
                if now - last_reconcile >= RECONCILE_INTERVAL_SECONDS:
                    _reconcile_once(db)
                    last_reconcile = now
                concurrency, poll_seconds = get_ragas_eval_worker_settings(db)
                futures = {future for future in futures if not future.done()}
                while len(futures) < concurrency and not stop_requested:
                    futures.add(executor.submit(_process_one_in_session, worker_id))
                time.sleep(poll_seconds)
            except Exception:
                db.rollback()
                logger.exception("kb-ragas-eval loop failed")
                time.sleep(DEFAULT_POLL_SECONDS)
            finally:
                db.close()
    logger.info("kb-ragas-eval stopping; no new jobs will be claimed", worker_id=worker_id)


if __name__ == "__main__":
    main()
