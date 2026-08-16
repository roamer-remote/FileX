# Copyright (c) 2026 徐泽宇
"""Consume kb.post queue and run entity/SAG/RAPTOR post-processing (114)."""

from __future__ import annotations

import structlog

from config import RABBITMQ_URL
from database import SessionLocal, init_db
from logging_setup import setup_logging
from messaging.kb_post_consumer import replay_queued_post_jobs, run_consumer
from services.kb_post_service import reconcile_stale_kb_post_jobs

setup_logging(service_name="kb-post")
logger = structlog.get_logger("kb_post")


def main() -> None:
    if not RABBITMQ_URL:
        raise SystemExit("RABBITMQ_URL 未设置，无法启动 kb-post")

    init_db(migrate=False)

    db = SessionLocal()
    try:
        stats = reconcile_stale_kb_post_jobs(db)
        if any(stats.values()):
            db.commit()
            logger.info("startup reconciled stale kb post state", **stats)
        replay_queued_post_jobs(db, full=True)
    finally:
        db.close()

    logger.info("kb-post started (RabbitMQ consumer)")
    from messaging.settings_invalidate_consumer import start_settings_invalidate_consumer

    start_settings_invalidate_consumer(service="kb-post")
    run_consumer()


if __name__ == "__main__":
    main()
