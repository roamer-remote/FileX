# Copyright (c) 2026 徐泽宇
"""OKF log_sync unit tests."""

from models.kb_log_entry import KbLogEntry
from services.okf.log_sync import import_log_entries, parse_log_md, render_log_md


def test_parse_log_md_extracts_bullets():
    text = "## 2026-06-23\n* **Creation**: Added [orders](/tables/orders.md).\n"
    entries = parse_log_md(text)
    assert len(entries) == 1
    assert "Creation" in entries[0]


def test_import_log_entries_idempotent(db_session, regular_user):
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)
    entry = "**Creation**: test entry"
    n1 = import_log_entries(db_session, regular_user.id, ws.id, [entry])
    n2 = import_log_entries(db_session, regular_user.id, ws.id, [entry])
    assert n1 == 1
    assert n2 == 0
    count = (
        db_session.query(KbLogEntry)
        .filter(
            KbLogEntry.user_id == regular_user.id,
            KbLogEntry.workspace_id == ws.id,
            KbLogEntry.entry == entry,
        )
        .count()
    )
    assert count == 1


def test_render_log_md_groups_by_date(db_session, regular_user):
    from services.kb_log_service import append_kb_log
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)
    append_kb_log(db_session, regular_user.id, "**Update**: item", workspace_id=ws.id)
    text = render_log_md(db_session, regular_user.id, ws.id)
    assert "# Directory Update Log" in text
    assert "**Update**" in text
