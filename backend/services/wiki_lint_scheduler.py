# Copyright (c) 2026 徐泽宇
"""定时 Wiki Lint（lifespan 后台协程）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from database import SessionLocal
from models.operation_log import OperationLog
from models.user import User
from services.system_setting_service import get_kb_wiki_lint_interval_hours
from services.wiki_lint_service import lint_all_users_with_kb_index

logger = logging.getLogger(__name__)

ADVISORY_LOCK_KEY = 900009


async def wiki_lint_scheduler_loop() -> None:
    while True:
        db = SessionLocal()
        try:
            hours = get_kb_wiki_lint_interval_hours(db)
            if hours <= 0:
                await asyncio.sleep(3600)
                continue
            got = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}).scalar()
            if not got:
                await asyncio.sleep(hours * 3600)
                continue
            try:
                reports = lint_all_users_with_kb_index(db)
                broken = sum(len(r.get("broken_links", [])) for r in reports)
                admin = db.query(User).filter(User.is_admin.is_(True), User.is_active.is_(True)).order_by(User.id).first()
                if admin:
                    db.add(
                        OperationLog(
                            user_id=admin.id,
                            action="kb_wiki_lint_scheduled",
                            target_type="kb_wiki",
                            target_id=0,
                            detail=f"users={len(reports)} broken={broken}",
                        )
                    )
                db.commit()
            finally:
                db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
        except Exception:
            logger.exception("wiki_lint_scheduler failed")
            db.rollback()
        finally:
            db.close()
        await asyncio.sleep(max(1, hours) * 3600)
