# Copyright (c) 2026 徐泽宇
"""extracted_at uses Beijing naive wall clock, not UTC."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from utils.timezone import BEIJING_TZ, to_beijing_time


def test_persist_extract_markdown_sets_beijing_naive(db_session, regular_user, tmp_path, monkeypatch):
    from models.file import File as FileModel
    from services.kb_extract_service import persist_extract_markdown

    upload = tmp_path / "uploads"
    upload.mkdir()
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(upload))
    monkeypatch.setattr("config.UPLOAD_DIR", str(upload))

    f = FileModel(
        filename="a.pdf",
        original_name="a.pdf",
        file_path=str(upload / "a.pdf"),
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    fixed = datetime(2026, 6, 25, 18, 30, 0, tzinfo=BEIJING_TZ)
    with patch("services.kb_extract_service.naive_db_now", return_value=fixed.replace(tzinfo=None)):
        with patch("services.md_tag_anchor_service.rebuild_anchors_for_file"):
            with patch("services.md_note_service.rebuild_md_note_side_effects"):
                persist_extract_markdown(db_session, f, "# hello\n", engine="liteparse+rapidocr", user_id=regular_user.id)

    assert f.extracted_at == datetime(2026, 6, 25, 18, 30, 0)
    shown = to_beijing_time(f.extracted_at)
    assert shown is not None
    assert shown.hour == 18


def test_extract_notify_payload_extracted_at_beijing_iso():
    from unittest.mock import MagicMock

    from messaging.kb_extract_publisher import file_extract_notify_payload

    f = MagicMock()
    f.id = 1
    f.user_id = 1
    f.index_status = "ready"
    f.chunk_count = 0
    f.index_error = None
    f.extract_status = "ready"
    f.extract_error = None
    f.has_md = True
    f.md_file_path = None
    f.extract_engine = "liteparse+rapidocr"
    f.mime_type = "application/pdf"
    f.original_name = "a.pdf"
    f.extracted_at = datetime(2026, 6, 25, 18, 30, 0)

    payload = file_extract_notify_payload(f)
    assert payload["extracted_at"] is not None
    assert "+08:00" in payload["extracted_at"]
    assert "18:30:00" in payload["extracted_at"]
