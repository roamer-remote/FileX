# Copyright (c) 2026 徐泽宇
"""007 P2: index chunks include original filename prefix.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_index_job import KbIndexJob
from services.kb_index_service import run_index_job


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
@patch("services.kb_index_service.resolve_index_text")
def test_run_index_job_prefixes_filename(mock_resolve, mock_embed, _mock_notify, db_session, regular_user):
    mock_resolve.return_value = ("正文内容", "sidecar_md")
    from config import OLLAMA_EMBED_DIM

    mock_embed.side_effect = lambda texts, **_kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]

    f = FileModel(
        filename="a",
        original_name="发票汇总.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        index_status="pending",
    )
    db_session.add(f)
    db_session.commit()
    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="queued")
    db_session.add(job)
    db_session.commit()

    run_index_job(db_session, job)

    chunks = db_session.query(KbChunk).filter(KbChunk.file_id == f.id).order_by(KbChunk.chunk_index).all()
    assert chunks
    assert chunks[0].text.startswith("【发票汇总.pdf】")
