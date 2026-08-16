# Copyright (c) 2026 徐泽宇
"""007 P3: CJK query expansion.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_search_expansion import expand_query_terms
from services.kb_search_service import search_kb
from services.system_setting_service import KEY_KB_SEARCH_HYBRID_ENABLED, invalidate_settings_cache, update_settings


def test_expand_query_terms_invoice():
    terms, expanded = expand_query_terms("发票")
    assert "发票" in expanded
    assert "报销" in expanded
    assert terms == expanded


def test_expand_query_skips_long_query():
    terms, expanded = expand_query_terms("这是一个很长的查询")
    assert terms == ["这是一个很长的查询"]
    assert expanded == []


@patch("services.kb_search_service.embed_text")
def test_search_meta_includes_expanded_terms(mock_embed, db_session, regular_user):
    from config import OLLAMA_EMBED_DIM

    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    invalidate_settings_cache()
    mock_embed.return_value = [0.5] * OLLAMA_EMBED_DIM

    f = FileModel(
        filename="a",
        original_name="doc.pdf",
        file_path="/tmp/a",
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
            text="报销流程",
            char_start=0,
            char_end=4,
            embedding=[0.5] * OLLAMA_EMBED_DIM,
            embedding_model="test-model",
        )
    )
    db_session.commit()

    _, _, _, meta = search_kb(
        db_session,
        regular_user.id,
        "发票",
        query_expansion=True,
        debug=True,
    )
    assert meta["query_expansion_enabled"] is True
    assert "报销" in meta["expanded_terms"]
