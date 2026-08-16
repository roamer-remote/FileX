# Copyright (c) 2026 徐泽宇
"""OKF log.md ↔ kb_log_entries."""

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy.orm import Session

from models.kb_log_entry import KbLogEntry
from services.kb_log_service import append_kb_log
from utils.timezone import to_beijing_time

_LOG_ENTRY_RE = re.compile(r"^\*\s+(.+)$", re.MULTILINE)


def parse_log_md(body: str) -> list[str]:
    """Extract bullet entries from OKF log.md body (SPEC §7)."""
    entries: list[str] = []
    for line in (body or "").splitlines():
        m = _LOG_ENTRY_RE.match(line.strip())
        if not m:
            continue
        text = m.group(1).strip()
        if text:
            entries.append(text)
    return entries


def import_log_entries(
    db: Session,
    user_id: int,
    workspace_id: int | None,
    entries: list[str],
) -> int:
    imported = 0
    for entry in entries:
        exists = (
            db.query(KbLogEntry)
            .filter(
                KbLogEntry.user_id == user_id,
                KbLogEntry.workspace_id == workspace_id,
                KbLogEntry.entry == entry,
            )
            .first()
        )
        if exists:
            continue
        append_kb_log(db, user_id, entry, workspace_id=workspace_id)
        imported += 1
    return imported


def render_log_md(db: Session, user_id: int, workspace_id: int | None) -> str:
    rows = (
        db.query(KbLogEntry)
        .filter(KbLogEntry.user_id == user_id, KbLogEntry.workspace_id == workspace_id)
        .order_by(KbLogEntry.created_at.desc())
        .all()
    )
    if not rows:
        return "# Directory Update Log\n"
    by_date: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        dt = row.created_at
        if dt is None:
            continue
        key = to_beijing_time(dt).strftime("%Y-%m-%d")
        by_date[key].append(f"* {row.entry}")
    lines = ["# Directory Update Log", ""]
    for date_key in sorted(by_date.keys(), reverse=True):
        lines.append(f"## {date_key}")
        lines.extend(by_date[date_key])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
