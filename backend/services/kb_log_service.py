# Copyright (c) 2026 徐泽宇
"""kb_log_entries 读写。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.kb_log_entry import KbLogEntry
from utils.timezone import to_beijing_time


def append_kb_log(
    db: Session,
    user_id: int,
    entry: str,
    *,
    workspace_id: int | None = None,
) -> KbLogEntry:
    row = KbLogEntry(user_id=user_id, workspace_id=workspace_id, entry=entry.strip())
    db.add(row)
    db.flush()
    return row


def list_kb_log(
    db: Session,
    user_id: int,
    *,
    workspace_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    q = db.query(KbLogEntry).filter(KbLogEntry.user_id == user_id)
    if workspace_id is not None:
        q = q.filter(KbLogEntry.workspace_id == workspace_id)
    total = q.count()
    rows = q.order_by(KbLogEntry.created_at.desc()).offset(offset).limit(limit).all()
    items = [
        {
            "id": r.id,
            "entry": r.entry,
            "workspace_id": r.workspace_id,
            "created_at": to_beijing_time(r.created_at).isoformat() if r.created_at else "",
        }
        for r in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}
