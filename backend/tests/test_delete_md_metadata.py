# Copyright (c) 2026 徐泽宇
"""Delete MD note clears extract metadata."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from models.file import File as FileModel
from services.md_paths import md_note_path


@pytest.fixture
def file_with_md(db_session, regular_user, tmp_path, monkeypatch):
    upload = tmp_path / "uploads"
    md_dir = upload / ".md_notes"
    md_dir.mkdir(parents=True)
    monkeypatch.setattr("services.md_paths.UPLOAD_DIR", str(upload))
    monkeypatch.setattr("config.UPLOAD_DIR", str(upload))

    f = FileModel(
        filename="doc.pdf",
        original_name="doc.pdf",
        file_path=str(upload / "doc.pdf"),
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        extract_status="ready",
        extract_engine="liteparse+rapidocr",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    note = Path(md_note_path(f.id))
    note.write_text("# note\n", encoding="utf-8")
    f.md_file_path = str(note)
    from datetime import datetime

    f.extracted_at = datetime.utcnow()
    f.md_content_hash = "abc123"
    db_session.commit()
    return f


@patch("messaging.kb_extract_publisher.publish_file_extract_notify")
def test_delete_md_clears_extract_metadata(mock_notify, client, jwt_token, db_session, file_with_md):
    f = file_with_md
    r = client.delete(
        f"/api/files/{f.id}/md",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    db_session.refresh(f)
    assert f.has_md is False
    assert f.md_file_path is None
    assert f.extracted_at is None
    assert f.extract_engine is None
    assert f.md_content_hash is None
    mock_notify.assert_called_once()
