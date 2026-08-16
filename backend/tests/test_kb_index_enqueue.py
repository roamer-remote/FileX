# Copyright (c) 2026 徐泽宇
"""MD save / delete triggers index enqueue.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import os
from unittest.mock import patch

from models.file import File as FileModel
from services.kb_text_source import resolve_index_text


def test_resolve_main_md_after_sidecar_cleared(db_session, regular_user, tmp_path):
    md_main = tmp_path / "note.md"
    md_main.write_text("# Main only\n\ncontent here", encoding="utf-8")
    f = FileModel(
        filename="note.md",
        original_name="note.md",
        file_path=str(md_main),
        file_size=10,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=False,
        md_file_path=None,
        index_status="skipped",
    )
    db_session.add(f)
    db_session.commit()
    text, src = resolve_index_text(f)
    assert text
    assert src == "main_md"
