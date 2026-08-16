# Copyright (c) 2026 徐泽宇
"""025: index persists chunk location from sidecar markers."""

from __future__ import annotations

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from services.kb_chunking import chunk_markdown
from services.kb_index_service import run_index_job
from services.extract.loc_markers import format_pdf_page_marker


def _vec(seed=0.5):
    return [seed] * OLLAMA_EMBED_DIM


@patch("services.kb_embed_cache_service.embed_texts")
def test_chunk_markdown_inherits_pdf_page_loc(mock_embed, db_session, regular_user):
    mock_embed.return_value = [_vec()]
    body = format_pdf_page_marker(3) + "page three content"
    pieces = chunk_markdown(body)
    assert len(pieces) == 1
    assert pieces[0].loc_type == "pdf_page"
    assert pieces[0].loc_start == 3


@patch("services.kb_embed_cache_service.embed_texts")
@patch("services.kb_index_service.resolve_index_text")
def test_index_job_persists_loc_columns(
    mock_resolve, mock_embed, db_session, regular_user, tmp_path,
):
    mock_embed.return_value = [_vec(), _vec()]
    sidecar = format_pdf_page_marker(1) + "hello citation"
    mock_resolve.return_value = (sidecar, "sidecar_md")

    f = FileModel(
        filename="a.pdf",
        original_name="a.pdf",
        file_path=str(tmp_path / "a.pdf"),
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=str(tmp_path / "note.md"),
        index_status="pending",
    )
    db_session.add(f)
    db_session.commit()

    from models.kb_index_job import KbIndexJob

    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="queued")
    db_session.add(job)
    db_session.commit()

    run_index_job(db_session, job)
    db_session.refresh(f)

    from models.kb_chunk import KbChunk

    chunk = db_session.query(KbChunk).filter(
        KbChunk.file_id == f.id, KbChunk.loc_type == "pdf_page",
    ).first()
    assert chunk is not None
    assert chunk.loc_type == "pdf_page"
    assert chunk.loc_start == 1
