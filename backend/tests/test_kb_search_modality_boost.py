# Copyright (c) 2026 徐泽宇
"""030 P1: modality intent boost on content_kind."""

from __future__ import annotations

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_enums import ContentKind
from services.kb_search_modality import detect_modality_intent
from services.kb_search_service import search_kb
from services.kb_search_cache_service import build_scope_hash
from services.system_setting_service import (
    KEY_KB_SEARCH_HYBRID_ENABLED,
    KEY_KB_SEARCH_MODALITY_BOOST,
    KEY_KB_SEARCH_MODALITY_BOOST_ENABLED,
    invalidate_settings_cache,
    update_settings,
)


def _vec(a: float, b: float = 0.0) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = a
    if OLLAMA_EMBED_DIM > 1:
        v[1] = b
    return v


def test_detect_modality_intent_figure_chinese():
    assert ContentKind.figure.value in detect_modality_intent("示意图中的实验结果")


def test_detect_modality_intent_figure_no_false_positive():
    assert ContentKind.figure.value not in detect_modality_intent("图书馆")
    assert ContentKind.figure.value not in detect_modality_intent("意图")
    assert ContentKind.table.value not in detect_modality_intent("表示")
    assert ContentKind.table.value not in detect_modality_intent("表达")


def test_detect_modality_intent_table_english():
    assert ContentKind.table.value in detect_modality_intent("summary table in report")


def test_build_scope_hash_includes_modality_boost():
    h_off = build_scope_hash(
        workspace_id=1,
        allowed_file_ids={1, 2},
        top_k=8,
        file_ids=None,
        tags=None,
        tag_mode="or",
        tag_combine="filter",
        hybrid=True,
        filename_boost=False,
        modality_boost=False,
        query_expansion=False,
        include_not_ready=False,
        include_drafts=False,
        group_by_file=False,
        context_chunks=0,
    )
    h_on = build_scope_hash(
        workspace_id=1,
        allowed_file_ids={1, 2},
        top_k=8,
        file_ids=None,
        tags=None,
        tag_mode="or",
        tag_combine="filter",
        hybrid=True,
        filename_boost=False,
        modality_boost=True,
        query_expansion=False,
        include_not_ready=False,
        include_drafts=False,
        group_by_file=False,
        context_chunks=0,
    )
    assert h_off != h_on


@patch("services.kb_search_service.embed_text")
def test_modality_boost_raises_figure_hit(mock_embed, db_session, regular_user):
    update_settings(
        db_session,
        {
            KEY_KB_SEARCH_HYBRID_ENABLED: "false",
            KEY_KB_SEARCH_MODALITY_BOOST: "0.25",
            KEY_KB_SEARCH_MODALITY_BOOST_ENABLED: "true",
        },
    )
    invalidate_settings_cache()
    mock_embed.return_value = _vec(1.0, 0.0)

    f_fig = FileModel(
        filename="a",
        original_name="实验报告.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    f_text = FileModel(
        filename="b",
        original_name="实验报告.pdf",
        file_path="/tmp/b",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add_all([f_fig, f_text])
    db_session.commit()

    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f_fig.id,
            chunk_index=0,
            source="sidecar_md",
            text="示意图说明",
            content_kind=ContentKind.figure.value,
            content_meta={"page_idx": 1},
            char_start=0,
            char_end=6,
            embedding=_vec(0.55, 0.84),
            embedding_model="test-model",
        )
    )
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f_text.id,
            chunk_index=0,
            source="sidecar_md",
            text="文中示意图文字描述",
            content_kind=ContentKind.text.value,
            char_start=0,
            char_end=8,
            embedding=_vec(0.58, 0.82),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    items_off, _, _, _ = search_kb(
        db_session, regular_user.id, "示意图", top_k=8, modality_boost=False,
    )
    assert items_off[0]["file_id"] == f_text.id

    items_on, _, _, meta = search_kb(
        db_session,
        regular_user.id,
        "示意图",
        top_k=8,
        modality_boost=True,
        debug=True,
    )
    assert items_on[0]["file_id"] == f_fig.id
    assert items_on[0].get("modality_boost") == 0.25
    assert meta["modality_boost_enabled"] is True
    assert meta["modality_boost_value"] == 0.25
    assert ContentKind.figure.value in meta["modality_intent"]


@patch("services.kb_search_service.embed_text")
def test_modality_boost_off_has_no_field(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(1.0, 0.0)
    f = FileModel(
        filename="a",
        original_name="报告.pdf",
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
            text="图片说明",
            content_kind=ContentKind.figure.value,
            char_start=0,
            char_end=4,
            embedding=_vec(0.5, 0.5),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    items, _, _, _ = search_kb(db_session, regular_user.id, "图片", top_k=8, modality_boost=False)
    assert "modality_boost" not in items[0]
