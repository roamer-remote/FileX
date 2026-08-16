# Copyright (c) 2026 徐泽宇
"""Consume kb.extract queue and run text extraction (run: python -m workers.kb_extract).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import structlog

from config import RABBITMQ_URL
from database import SessionLocal, init_db
from logging_setup import setup_logging
from messaging.kb_extract_consumer import replay_queued_jobs, run_consumer
from services.kb_extract_service import reconcile_stale_kb_extract_jobs

setup_logging(service_name="kb-extract")
logger = structlog.get_logger("kb_extract")


def main() -> None:
    if not RABBITMQ_URL:
        raise SystemExit("RABBITMQ_URL 未设置，无法启动 kb-extract")

    init_db(migrate=False)

    db = SessionLocal()
    try:
        from services.mineru_auto_enable_service import maybe_auto_enable_mineru_provider

        maybe_auto_enable_mineru_provider(db)
    finally:
        db.close()

    db = SessionLocal()
    try:
        n = reconcile_stale_kb_extract_jobs(db)
        if n:
            db.commit()
            logger.info("startup reconciled stale kb extract state", count=n)
        replay_queued_jobs(db, full=True)
    finally:
        db.close()

    from services.extract.liteparse_ocr_bridge import start_liteparse_ocr_bridge

    start_liteparse_ocr_bridge()

    logger.info("kb-extract started (RabbitMQ consumer)")
    from messaging.settings_invalidate_consumer import start_settings_invalidate_consumer

    start_settings_invalidate_consumer(service="kb-extract")
    run_consumer()


if __name__ == "__main__":
    main()
