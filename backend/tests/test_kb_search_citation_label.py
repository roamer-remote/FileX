# Copyright (c) 2026 徐泽宇
"""025: search citation_label on hits."""

from __future__ import annotations

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_search_service import search_kb


def _vec(seed=0.5):
    return [seed] * OLLAMA_EMBED_DIM


@patch("services.kb_search_service.embed_text")
def test_search_hit_includes_citation_label_without_citation_format(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec()
    f = FileModel(
        filename="a.pdf",
        original_name="合同.pdf",
        file_path="/tmp/a.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text="金额合计",
            char_start=0,
            char_end=4,
            loc_type="pdf_page",
            loc_start=7,
            loc_end=7,
            embedding=_vec(0.2),
            embedding_model="test",
        )
    )
    db_session.commit()

    items, _, _, _ = search_kb(db_session, regular_user.id, "金额", top_k=3)
    assert items[0]["citation_label"] == "《合同.pdf》第 7 页"
    assert items[0]["citation_tier"] == "paginated"
    assert items[0]["location"]["page"] == 7
    assert "citation" not in items[0]


@patch("services.kb_search_service.embed_text")
def test_search_docx_document_only_label(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec()
    f = FileModel(
        filename="a.docx",
        original_name="说明.docx",
        file_path="/tmp/a.docx",
        file_size=1,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text="概述",
            char_start=0,
            char_end=2,
            embedding=_vec(0.2),
            embedding_model="test",
        )
    )
    db_session.commit()

    items, _, _, _ = search_kb(db_session, regular_user.id, "概述", top_k=3)
    assert items[0]["citation_label"] == "《说明.docx》"
    assert items[0]["citation_tier"] == "document_only"
    assert items[0]["location"] is None


@patch("services.kb_search_service.embed_text")
def test_search_citation_format_adds_agent_citation(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec()
    f = FileModel(
        filename="a.md",
        original_name="a.md",
        file_path="/tmp/a.md",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text="cite me",
            char_start=0,
            char_end=7,
            embedding=_vec(0.1),
            embedding_model="test",
        )
    )
    db_session.commit()
    items, _, _, _ = search_kb(
        db_session, regular_user.id, "cite", top_k=3, citation_format="markdown",
    )
    assert items[0]["citation_label"] == "《a.md》"
    assert "citation" in items[0]
    assert "filex://file/" in items[0]["citation"]
