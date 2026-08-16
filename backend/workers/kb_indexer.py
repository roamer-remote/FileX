# Copyright (c) 2026 徐泽宇
"""Consume kb.index queue and run vector indexing (run: python -m workers.kb_indexer).

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
from messaging.kb_index_consumer import replay_queued_jobs, run_consumer
from services.kb_index_service import reconcile_stale_kb_index_jobs
from services.kb_ollama_embed import log_ollama_startup

setup_logging(service_name="kb-indexer")
logger = structlog.get_logger("kb_indexer")


def main() -> None:
    if not RABBITMQ_URL:
        raise SystemExit("RABBITMQ_URL 未设置，无法启动 kb-indexer")

    init_db(migrate=False)
    log_ollama_startup()

    db = SessionLocal()
    try:
        stats = reconcile_stale_kb_index_jobs(db)
        if any(stats.values()):
            db.commit()
            logger.info("startup reconciled stale kb index state", **stats)
        replay_queued_jobs(db, full=True)
    finally:
        db.close()

    logger.info("kb-indexer started (RabbitMQ serial consumer)")
    from messaging.settings_invalidate_consumer import start_settings_invalidate_consumer

    start_settings_invalidate_consumer(service="kb-indexer")
    run_consumer()


if __name__ == "__main__":
    main()
