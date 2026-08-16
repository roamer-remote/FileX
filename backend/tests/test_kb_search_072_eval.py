# Copyright (c) 2026 徐泽宇
"""072 P2 T-F1：007 评测集扩展 — 标签+Wiki 互联用例（可重复 pytest）。"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_retrieval_hints_service import suggest_retrieval_hints
from services.system_setting_service import (
    KEY_KB_SEARCH_HYBRID_ENABLED,
    KEY_KB_SEARCH_TAG_COOC_ENABLED,
    KEY_KB_SEARCH_TAG_COOC_MIN_EDGE,
    invalidate_settings_cache,
    update_settings,
)
from services.tag_service import replace_file_tags
from services.workspace_service import ensure_personal_workspace

_EVAL_CASES = Path(__file__).resolve().parent / "fixtures" / "kb_search_072_tag_wiki_eval_cases.json"


def _vec(seed: float) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


@pytest.fixture(autouse=True)
def _kb_settings(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_SEARCH_HYBRID_ENABLED: "false",
            KEY_KB_SEARCH_TAG_COOC_ENABLED: "true",
            KEY_KB_SEARCH_TAG_COOC_MIN_EDGE: "1",
        },
    )
    db_session.commit()
    invalidate_settings_cache()
    yield


def _add_source(db_session, user_id, tmp_path, name, md5, **extra):
    p = tmp_path / name
    p.write_text("x", encoding="utf-8")
    f = FileModel(
        user_id=user_id,
        filename=name,
        original_name=name,
        file_path=str(p),
        file_size=1,
        mime_type="text/plain",
        md5_hash=md5,
        has_md=False,
        index_status="ready",
        page_kind="source",
        publish_status="published",
        **extra,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def _add_chunk(db_session, user_id, file_id, text, seed=0.5):
    db_session.add(
        KbChunk(
            user_id=user_id,
            file_id=file_id,
            chunk_index=0,
            source="sidecar_md",
            text=text,
            char_start=0,
            char_end=len(text),
            embedding=_vec(seed),
            embedding_model="test-model",
        )
    )
    db_session.commit()


@patch("services.kb_search_service.embed_text")
def test_eval_072_tag_topic_profile_and_combined_flags(
    mock_embed, db_session, regular_user, tmp_path, client, jwt_token
):
    """072 T-F1：TAG_TOPIC Profile + wiki/cooc 组合参数 API 可接受。"""
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "072eval tag wiki profile"
    seed = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "072_seed.txt",
        "a" * 32,
        workspace_id=personal.id,
    )
    _add_chunk(db_session, regular_user.id, seed.id, f"{query} seed chunk", seed=0.9)

    hints = suggest_retrieval_hints("相邻标签共现的主题")
    assert hints["query_type"] == "tag_topic"
    assert hints["search_params"]["expand_tag_cooc"] is True
    assert hints["search_params"]["wiki_context_depth"] == 1

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        params={"workspace_id": personal.id},
        json={
            "query": query,
            "top_k": 5,
            "expand_wiki_links": True,
            "expand_wiki_coref": False,
            "wiki_context_depth": 1,
            "expand_tag_cooc": True,
            "group_by_file": True,
            "debug": True,
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) >= 1


@patch("services.kb_search_service.embed_text")
def test_eval_wiki_graph_expand_with_tags(mock_embed, db_session, regular_user, tmp_path, client, jwt_token):
    """072：L4a wiki_graph + 标签过滤 filter 模式。"""
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    query = "072eval wikigraph tag"
    a = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "072_wg_a.txt",
        "c" * 32,
        workspace_id=personal.id,
    )
    b = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "072_wg_b.txt",
        "d" * 32,
        workspace_id=personal.id,
    )
    replace_file_tags(db_session, regular_user.id, a.id, ["topic072"])
    replace_file_tags(db_session, regular_user.id, b.id, ["topic072"])
    db_session.commit()
    _add_chunk(db_session, regular_user.id, a.id, f"{query} alpha", seed=0.9)
    _add_chunk(db_session, regular_user.id, b.id, f"{query} beta linked", seed=0.3)
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": f"[[file:{b.id}]]\n"},
    )

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        params={"workspace_id": personal.id},
        json={
            "query": query,
            "top_k": 8,
            "expand_wiki_graph": True,
            "tags": ["topic072"],
            "tag_combine": "filter",
            "group_by_file": True,
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) >= 1


def test_eval_cases_file_matches_hints():
    """007 golden 扩展：JSON 用例 query_type 与 retrieval-hints 一致。"""
    if not _EVAL_CASES.is_file():
        pytest.skip("no 072 eval cases file")
    cases = json.loads(_EVAL_CASES.read_text(encoding="utf-8"))
    for case in cases:
        hints = suggest_retrieval_hints(case["query"])
        assert hints["query_type"] == case["expected_query_type"]
