# Copyright (c) 2026 徐泽宇
"""share_links.expires_at uses Beijing naive wall clock, not UTC."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from models.file import File as FileModel
from services.share_service import create_share_link, get_share_by_token
from utils.timezone import BEIJING_TZ, to_beijing_time


def test_create_share_link_expires_at_beijing_naive(db_session, regular_user, tmp_path):
    file_path = tmp_path / "share.pdf"
    file_path.write_bytes(b"%PDF")
    f = FileModel(
        user_id=regular_user.id,
        filename="share.pdf",
        original_name="share.pdf",
        file_path=str(file_path),
        file_size=4,
        mime_type="application/pdf",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    fixed = datetime(2026, 7, 2, 16, 0, 0, tzinfo=BEIJING_TZ)
    with patch("services.share_service.naive_db_now", return_value=fixed.replace(tzinfo=None)):
        share = create_share_link(db_session, f.id, regular_user.id, expires_in_hours=24)

    assert share.expires_at == datetime(2026, 7, 3, 16, 0, 0)
    shown = to_beijing_time(share.expires_at)
    assert shown is not None
    assert shown.hour == 16

    with patch("services.share_service.naive_db_now", return_value=datetime(2026, 7, 3, 15, 59, 0)):
        assert get_share_by_token(db_session, share.token) is not None
    with patch("services.share_service.naive_db_now", return_value=datetime(2026, 7, 3, 16, 0, 1)):
        assert get_share_by_token(db_session, share.token) is None
