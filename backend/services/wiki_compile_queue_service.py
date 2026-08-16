# Copyright (c) 2026 徐泽宇
"""Wiki 概念页编译队列与可选 Webhook。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import httpx
from sqlalchemy.orm import Session

from config import FILEX_WIKI_COMPILE_WEBHOOK_URL
from models.user import User
from models.wiki_compile_queue import WikiCompileQueue
from services.system_setting_service import get_kb_wiki_compile_min_sources
from services.wiki_candidate_service import list_pending_concept_slugs

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_SEC = 2.0


def sync_compile_queue_after_md_save(db: Session, actor: User, workspace_id: int | None) -> None:
    """save md 后 upsert pending 行；可选 webhook（不阻塞）。"""
    if workspace_id is None:
        return
    min_sources = get_kb_wiki_compile_min_sources(db, user_id=actor.id)
    pending = list_pending_concept_slugs(
        db, actor, workspace_id, min_sources=min_sources
    )
    if not pending:
        return
    for item in pending:
        slug = item["wiki_slug"]
        count = int(item["source_count"])
        row = (
            db.query(WikiCompileQueue)
            .filter(
                WikiCompileQueue.user_id == actor.id,
                WikiCompileQueue.workspace_id == workspace_id,
                WikiCompileQueue.wiki_slug == slug,
                WikiCompileQueue.status == "pending",
            )
            .first()
        )
        if row:
            row.source_count = count
        else:
            db.add(
                WikiCompileQueue(
                    user_id=actor.id,
                    workspace_id=workspace_id,
                    wiki_slug=slug,
                    source_count=count,
                    status="pending",
                )
            )
    db.flush()
    _fire_webhook_async(actor.id, workspace_id, pending)


def list_compile_queue(
    db: Session,
    user: User,
    workspace_id: int | None,
    *,
    status: str = "pending",
) -> list[WikiCompileQueue]:
    q = db.query(WikiCompileQueue).filter(WikiCompileQueue.user_id == user.id)
    if workspace_id is not None:
        q = q.filter(WikiCompileQueue.workspace_id == workspace_id)
    if status:
        q = q.filter(WikiCompileQueue.status == status)
    return q.order_by(WikiCompileQueue.updated_at.desc()).all()


def patch_compile_queue_status(
    db: Session,
    user: User,
    queue_id: int,
    status: str,
) -> WikiCompileQueue | None:
    if status not in ("done", "skipped", "pending"):
        raise ValueError("status 无效")
    row = (
        db.query(WikiCompileQueue)
        .filter(WikiCompileQueue.id == queue_id, WikiCompileQueue.user_id == user.id)
        .first()
    )
    if not row:
        return None
    row.status = status
    db.flush()
    return row


def _fire_webhook_async(user_id: int, workspace_id: int | None, items: list[dict[str, Any]]) -> None:
    url = (FILEX_WIKI_COMPILE_WEBHOOK_URL or "").strip()
    if not url:
        return
    payload = {
        "event": "wiki_compile_pending",
        "user_id": user_id,
        "workspace_id": workspace_id,
        "items": items,
    }

    def _post() -> None:
        try:
            with httpx.Client(timeout=WEBHOOK_TIMEOUT_SEC) as client:
                client.post(url, json=payload)
        except Exception as exc:
            logger.warning("wiki compile webhook failed: %s", exc)

    threading.Thread(target=_post, daemon=True).start()
