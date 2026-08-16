# Copyright (c) 2026 徐泽宇
"""Runtime toggle for kb_search_hybrid_enabled.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_search_service import search_kb
from services.system_setting_service import (
    KEY_KB_SEARCH_HYBRID_ENABLED,
    get_public_settings_dict,
    is_kb_search_hybrid_enabled,
    update_settings,
)


def _vec(seed: float) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


def test_kb_search_hybrid_default_constant():
    from services.system_setting_service import DEFAULTS
    assert DEFAULTS[KEY_KB_SEARCH_HYBRID_ENABLED] == "true"


def test_update_settings_kb_search_hybrid_enabled(db_session):
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "true"})
    d = get_public_settings_dict(db_session)
    assert d["kb_search_hybrid_enabled"] == "true"
    assert is_kb_search_hybrid_enabled(db_session) is True

    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    assert is_kb_search_hybrid_enabled(db_session) is False


def test_update_settings_rejects_invalid_hybrid_value(db_session):
    with pytest.raises(ValueError, match="kb_search_hybrid_enabled"):
        update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "maybe"})


@patch("services.kb_search_service.embed_text")
def test_search_keyword_guard_follows_runtime_hybrid_setting(mock_embed, db_session, regular_user):
    """关：短词须字面命中；开：关闭 keyword guard，纯向量可召回大小写不一致片段。"""
    mock_embed.return_value = _vec(0.9)
    f = FileModel(
        filename="a.md",
        original_name="OpenClaw.md",
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
            source="main_md",
            text="OpenClaw agent framework",
            char_start=0,
            char_end=24,
            embedding=_vec(0.1),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    items_off, _, _, _meta = search_kb(db_session, regular_user.id, "openclaw", top_k=5)
    assert items_off == []

    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "true"})
    items_on, _, _, _meta = search_kb(db_session, regular_user.id, "openclaw", top_k=5)
    assert len(items_on) == 1
    assert items_on[0]["file_id"] == f.id

    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
