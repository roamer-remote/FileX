# Copyright (c) 2026 徐泽宇
"""indexed_at uses Beijing naive wall clock, not UTC (align with extracted_at)."""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import patch

from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_index_job import KbIndexJob
from services.kb_index_service import run_index_job
from utils.timezone import BEIJING_TZ, to_beijing_time


def test_run_index_job_sets_beijing_naive_indexed_at(db_session, regular_user):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, "indexed_at_tz.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# Title\n\nParagraph.\n")

    f = FileModel(
        filename="x.png",
        original_name="x.png",
        file_path="/tmp/unused.png",
        file_size=10,
        mime_type="image/png",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=md_path,
        extract_status="ready",
        index_status="pending",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="queued", force=True)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    fixed = datetime(2026, 7, 2, 16, 45, 19, tzinfo=BEIJING_TZ)
    with patch("services.kb_index_service.naive_db_now", return_value=fixed.replace(tzinfo=None)):
        with patch("services.kb_index_service._notify_file_index"):
            with patch("services.kb_embed_cache_service.embed_texts") as mock_embed:
                mock_embed.side_effect = lambda texts, **_kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]
                run_index_job(db_session, job)

    db_session.commit()
    db_session.refresh(f)
    assert f.indexed_at == datetime(2026, 7, 2, 16, 45, 19)
    shown = to_beijing_time(f.indexed_at)
    assert shown is not None
    assert shown.hour == 16
    assert shown.minute == 45
