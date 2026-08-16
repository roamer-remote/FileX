# Copyright (c) 2026 徐泽宇
"""008: zhparser FTS config, long-query plainto skip, effective config fallback.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from config import KB_FTS_LONG_QUERY_LEN, OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_fts_service import (
    FTS_SIMPLE,
    FTS_ZH_CN,
    get_effective_fts_config,
    should_use_plainto_for_query,
    zhparser_installed,
)
from services.kb_search_service import search_kb
from services.system_setting_service import KEY_KB_FTS_CONFIG, KEY_KB_SEARCH_HYBRID_ENABLED, update_settings


def _vec(seed: float) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


def test_should_use_plainto_short_query():
    assert should_use_plainto_for_query("发票") is True
    assert should_use_plainto_for_query("a" * KB_FTS_LONG_QUERY_LEN) is True


def test_should_use_plainto_long_query():
    assert should_use_plainto_for_query("a" * (KB_FTS_LONG_QUERY_LEN + 1)) is False


def test_get_effective_fts_config_falls_back_without_zhparser(db_session):
    update_settings(db_session, {KEY_KB_FTS_CONFIG: FTS_ZH_CN})
    with patch("services.kb_fts_service.zhparser_installed", return_value=False):
        assert get_effective_fts_config(db_session) == FTS_SIMPLE


@patch("services.kb_search_service.embed_text")
def test_long_query_skips_plainto_tsquery(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(0.9)
    update_settings(
        db_session,
        {KEY_KB_SEARCH_HYBRID_ENABLED: "true", KEY_KB_FTS_CONFIG: FTS_ZH_CN},
    )

    f = FileModel(
        filename="a.md",
        original_name="说明.md",
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
            text="报销流程说明",
            char_start=0,
            char_end=6,
            embedding=_vec(0.5),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    long_q = "这是一段超过十个字符的 Agent 长句查询用于测试"
    assert len(long_q) > KB_FTS_LONG_QUERY_LEN

    with patch(
        "services.kb_search_service.func.plainto_tsquery",
        side_effect=AssertionError("long query must skip plainto_tsquery"),
    ):
        items, _, _, meta = search_kb(
            db_session,
            regular_user.id,
            long_q,
            top_k=5,
            hybrid=True,
            debug=True,
        )

    assert meta.get("effective_fts_config") in (FTS_ZH_CN, FTS_SIMPLE)
    assert isinstance(items, list)


def test_zh_cn_tsvector_plainto_integration(db_session):
    if not zhparser_installed(db_session):
        import pytest

        pytest.skip("zhparser extension not installed")
    from sqlalchemy import text

    row = db_session.execute(
        text("SELECT to_tsvector('zh_cn', '发票报销') @@ plainto_tsquery('zh_cn', '发票')")
    ).scalar()
    assert row is True
