# Copyright (c) 2026 徐泽宇
"""Index job heading_path cap integration tests (038 PR-1)."""

import os
from unittest.mock import patch

from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_index_job import KbIndexJob
from services.kb_chunking import TextChunk
from services.kb_heading_path import KB_HEADING_PATH_MAX_LEN
from services.kb_index_service import enqueue_index, run_index_job


def _make_file(db_session, user_id, md_body: str):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, f"heading_cap_{user_id}.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md_body)
    f = FileModel(
        filename="x.bin",
        original_name="paper.pdf",
        file_path="/tmp/unused.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=user_id,
        has_md=True,
        md_file_path=md_path,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def _run_job(db_session, f):
    job_id = enqueue_index(db_session, f.user_id, f.id)
    db_session.commit()
    job = db_session.query(KbIndexJob).filter(KbIndexJob.id == job_id).one()
    run_index_job(db_session, job)
    db_session.commit()
    db_session.refresh(f)
    return f


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
def test_index_job_caps_nested_long_heading_path(mock_embed, _mock_notify, db_session, regular_user):
    mock_embed.side_effect = lambda texts, **_kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]
    t150 = "章" * 150
    md = f"# {t150}\n\n## {t150}\n\n### {t150}\n\n#### {t150}\n\n段落正文。"
    f = _make_file(db_session, regular_user.id, md)
    f = _run_job(db_session, f)
    assert f.index_status == "ready"
    chunks = db_session.query(KbChunk).filter(KbChunk.file_id == f.id).all()
    assert chunks
    for ch in chunks:
        if ch.heading_path:
            assert len(ch.heading_path) <= KB_HEADING_PATH_MAX_LEN


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_index_service.chunk_markdown")
@patch("services.kb_embed_cache_service.embed_texts")
def test_index_job_caps_mock_injected_heading_path(mock_embed, mock_chunk_md, _mock_notify, db_session, regular_user):
    mock_embed.side_effect = lambda texts, **_kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]
    long_path = "p" * 600
    mock_chunk_md.return_value = [
        TextChunk(text="body", char_start=0, char_end=4, heading_path=long_path),
    ]
    f = _make_file(db_session, regular_user.id, "# x\n\nbody")
    f = _run_job(db_session, f)
    assert f.index_status == "ready"
    ch = db_session.query(KbChunk).filter(KbChunk.file_id == f.id).one()
    assert ch.heading_path is not None
    assert len(ch.heading_path) == KB_HEADING_PATH_MAX_LEN
