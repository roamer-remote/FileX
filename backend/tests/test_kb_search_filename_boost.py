# Copyright (c) 2026 徐泽宇
"""007 P1: filename substring boost.

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
from services.system_setting_service import (
    KEY_KB_SEARCH_FILENAME_BOOST,
    KEY_KB_SEARCH_HYBRID_ENABLED,
    invalidate_settings_cache,
    update_settings,
)


def _vec(a: float, b: float = 0.0) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = a
    if OLLAMA_EMBED_DIM > 1:
        v[1] = b
    return v


@patch("services.kb_search_service.embed_text")
def test_filename_boost_raises_named_file(mock_embed, db_session, regular_user):
    update_settings(
        db_session,
        {
            KEY_KB_SEARCH_HYBRID_ENABLED: "false",
            KEY_KB_SEARCH_FILENAME_BOOST: "0.20",
        },
    )
    invalidate_settings_cache()
    mock_embed.return_value = _vec(1.0, 0.0)

    f_name = FileModel(
        filename="a",
        original_name="2024年发票汇总.xlsx",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    f_body = FileModel(
        filename="b",
        original_name="费用报销制度.docx",
        file_path="/tmp/b",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add_all([f_name, f_body])
    db_session.commit()

    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f_name.id,
            chunk_index=0,
            source="sidecar_md",
            text="年度汇总表格",
            char_start=0,
            char_end=6,
            embedding=_vec(0.55, 0.84),
            embedding_model="test-model",
        )
    )
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f_body.id,
            chunk_index=0,
            source="sidecar_md",
            text="发票报销流程说明",
            char_start=0,
            char_end=8,
            embedding=_vec(0.58, 0.82),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    items_off, _, _, _ = search_kb(db_session, regular_user.id, "发票", top_k=8, filename_boost=False)
    assert items_off[0]["file_id"] == f_body.id

    items_on, _, _, meta = search_kb(
        db_session,
        regular_user.id,
        "发票",
        top_k=8,
        filename_boost=True,
        debug=True,
    )
    assert items_on[0]["file_id"] == f_name.id
    assert items_on[0].get("filename_boost") == 0.2
    assert meta["filename_boost_enabled"] is True
    assert meta["filename_boost_value"] == 0.2


@patch("services.kb_search_service.embed_text")
def test_filename_boost_off_has_no_field(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(1.0, 0.0)
    f = FileModel(
        filename="a",
        original_name="发票清单.pdf",
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
            text="content",
            char_start=0,
            char_end=7,
            embedding=_vec(0.5, 0.5),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    items, _, _, _ = search_kb(db_session, regular_user.id, "发票", filename_boost=False)
    assert "filename_boost" not in items[0]
