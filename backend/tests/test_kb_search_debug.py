# Copyright (c) 2026 徐泽宇
"""Search debug meta and citations.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_search_service import search_kb


def _vec(seed=0.5):
    return [seed] * OLLAMA_EMBED_DIM


@patch("services.kb_search_service.embed_text")
def test_search_debug_meta(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec()
    f = FileModel(
        filename="a",
        original_name="a.md",
        file_path="/tmp/a",
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
            text="hello world",
            char_start=0,
            char_end=11,
            embedding=_vec(0.1),
            embedding_model="test",
        )
    )
    db_session.commit()
    items, _, k, meta = search_kb(db_session, regular_user.id, "hello", top_k=5, debug=True)
    assert k == 5
    assert meta.get("debug") is True
    assert "hybrid_enabled" in meta
    assert items[0].get("chunk_id") is not None


@patch("services.kb_search_service.embed_text")
def test_search_citation_markdown(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec()
    f = FileModel(
        filename="a",
        original_name="a.md",
        file_path="/tmp/a",
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
    assert "citation" in items[0]
    assert "filex://file/" in items[0]["citation"]
