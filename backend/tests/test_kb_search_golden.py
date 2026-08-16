# Copyright (c) 2026 徐泽宇
"""Optional golden regression: KB_GOLDEN=1 and Ollama/embed mock."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_search_service import search_kb
from services.system_setting_service import KEY_KB_SEARCH_HYBRID_ENABLED, invalidate_settings_cache, update_settings

_GOLDEN_CASES = Path(__file__).resolve().parent / "fixtures" / "kb_search_golden_cases.json"


def _vec(a: float = 1.0) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = a
    return v


@patch("services.kb_search_service.embed_text")
def test_default_search_params_regression(mock_embed, db_session, regular_user):
    """SC-002：默认 API 参数下 search_kb 行为与 028 前一致（无 cache / monte_carlo）。"""
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    invalidate_settings_cache()
    mock_embed.return_value = _vec(0.9)

    f = FileModel(
        filename="a",
        original_name="回归测试.pdf",
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
            text="报销制度说明",
            char_start=0,
            char_end=6,
            embedding=_vec(0.95),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    items, _, k, meta = search_kb(db_session, regular_user.id, "报销", top_k=5, debug=True)
    assert k == 5
    assert len(items) >= 1
    assert items[0]["file_id"] == f.id
    assert "hybrid_enabled" in meta
    assert meta.get("cache_hit") is None
    assert meta.get("monte_carlo_sample_count") is None


@pytest.mark.skipif(os.environ.get("KB_GOLDEN") != "1", reason="KB_GOLDEN=1")
@patch("services.kb_search_service.embed_text")
def test_golden_cases_file(mock_embed, db_session, regular_user):
    if not _GOLDEN_CASES.is_file():
        pytest.skip("no golden cases file")
    cases = json.loads(_GOLDEN_CASES.read_text(encoding="utf-8"))
    mock_embed.return_value = _vec(0.5)
    for case in cases:
        items, _, _, meta = search_kb(
            db_session,
            regular_user.id,
            case["query"],
            top_k=5,
            debug=True,
        )
        assert len(items) >= int(case.get("min_hits", 0))
        assert "hybrid_enabled" in meta
