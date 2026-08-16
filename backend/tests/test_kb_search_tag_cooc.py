# Copyright (c) 2026 徐泽宇
"""072: search expand_tag_cooc RAG chunk 扩召回。

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
from services.kb_search_tag_cooc_service import (
    TAG_COOC_SCORE_FACTOR,
    _compute_tag_cooccurrence,
    expand_search_items_with_tag_cooc,
)
from services.system_setting_service import (
    KEY_KB_SEARCH_HYBRID_ENABLED,
    KEY_KB_SEARCH_TAG_COOC_ENABLED,
    KEY_KB_SEARCH_TAG_COOC_MIN_EDGE,
    invalidate_settings_cache,
    update_settings,
)
from services.tag_service import replace_file_tags
from services.workspace_service import ensure_personal_workspace


@pytest.fixture(autouse=True)
def _disable_hybrid(db_session):
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    db_session.commit()
    invalidate_settings_cache()
    yield


@pytest.fixture(autouse=True)
def _enable_tag_cooc(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_SEARCH_TAG_COOC_ENABLED: "true",
            KEY_KB_SEARCH_TAG_COOC_MIN_EDGE: "1",
        },
    )
    db_session.commit()
    invalidate_settings_cache()
    yield


def _vec(seed: float) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


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


def test_compute_tag_cooccurrence_min_edge(db_session, regular_user, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    seed = _add_source(
        db_session, regular_user.id, tmp_path, "seed.txt", "a" * 32, workspace_id=personal.id
    )
    peer = _add_source(
        db_session, regular_user.id, tmp_path, "peer.txt", "b" * 32, workspace_id=personal.id
    )
    replace_file_tags(db_session, regular_user.id, seed.id, ["alpha", "beta"])
    replace_file_tags(db_session, regular_user.id, peer.id, ["alpha"])
    db_session.commit()

    tags = _compute_tag_cooccurrence(
        db_session,
        regular_user,
        [seed.id],
        min_edge=2,
        max_tags=5,
        workspace_id=personal.id,
        cross_workspace=False,
        allowed_file_ids=None,
    )
    assert tags == []

    tags = _compute_tag_cooccurrence(
        db_session,
        regular_user,
        [seed.id],
        min_edge=1,
        max_tags=5,
        workspace_id=personal.id,
        cross_workspace=False,
        allowed_file_ids=None,
    )
    assert "alpha" in tags


@patch("services.kb_search_service.embed_text")
def test_expand_tag_cooc_adds_neighbor_chunks(
    mock_embed,
    db_session,
    regular_user,
    tmp_path,
):
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "tagcooc072seed"
    seed = _add_source(
        db_session, regular_user.id, tmp_path, "seed.txt", "c" * 32, workspace_id=personal.id
    )
    neighbor = _add_source(
        db_session, regular_user.id, tmp_path, "neighbor.txt", "d" * 32, workspace_id=personal.id
    )
    replace_file_tags(db_session, regular_user.id, seed.id, ["alpha", "beta"])
    replace_file_tags(db_session, regular_user.id, neighbor.id, ["beta", "gamma"])
    db_session.commit()

    _add_chunk(db_session, regular_user.id, seed.id, f"{query} seed chunk", seed=0.9)
    _add_chunk(db_session, regular_user.id, neighbor.id, f"{query} neighbor chunk", seed=0.4)

    primary, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        workspace_id=personal.id,
        file_ids=[seed.id],
        top_k=3,
        group_by_file=True,
    )
    assert len(primary) == 1

    merged, meta = expand_search_items_with_tag_cooc(
        db_session,
        regular_user,
        query,
        primary,
        user_id=regular_user.id,
        search_kwargs={"hybrid": False},
        workspace_id=personal.id,
        cross_workspace=False,
        allowed_file_ids=None,
        top_k=3,
        group_by_file=True,
        min_edge=1,
    )
    assert meta["tag_cooc_expanded"] is True
    assert "beta" in meta["tag_cooc_neighbor_tags"]
    fids = {row["file_id"] for row in merged}
    assert neighbor.id in fids
    neighbor_hit = next(x for x in merged if x["file_id"] == neighbor.id)
    assert neighbor_hit["source_kind"] == "tag_cooc_expand"
    raw, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        workspace_id=personal.id,
        file_ids=[neighbor.id],
        top_k=1,
        group_by_file=True,
        hybrid=False,
    )
    expected = round(float(raw[0]["score"]) * TAG_COOC_SCORE_FACTOR, 4)
    assert abs(float(neighbor_hit["score"]) - expected) < 1e-6


@patch("services.kb_search_tag_cooc_service._compute_tag_cooccurrence")
@patch("services.kb_search_service.embed_text")
def test_search_api_expand_tag_cooc(
    mock_embed,
    mock_cooc,
    client,
    db_session,
    regular_user,
    jwt_token,
    tmp_path,
):
    mock_embed.return_value = _vec(0.5)
    mock_cooc.return_value = ["topic-b"]
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "tagcooc072api"
    seed = _add_source(
        db_session, regular_user.id, tmp_path, "seed.txt", "e" * 32, workspace_id=personal.id
    )
    neighbor = _add_source(
        db_session, regular_user.id, tmp_path, "peer.txt", "f" * 32, workspace_id=personal.id
    )
    replace_file_tags(db_session, regular_user.id, seed.id, ["topic-a", "topic-b"])
    replace_file_tags(db_session, regular_user.id, neighbor.id, ["topic-b"])
    db_session.commit()
    _add_chunk(db_session, regular_user.id, seed.id, f"{query} seed", seed=0.9)
    _add_chunk(db_session, regular_user.id, neighbor.id, f"{query} peer chunk", seed=0.3)

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": query,
            "top_k": 5,
            "file_ids": [seed.id],
            "group_by_file": True,
            "expand_tag_cooc": True,
            "debug": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    meta = data["meta"] or {}
    assert meta.get("tag_cooc_expanded") is True
    fids = {item["file_id"] for item in data["items"]}
    assert neighbor.id in fids


def test_expand_tag_cooc_union_mutex_422(client, jwt_token):
    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": "mutex test",
            "expand_tag_cooc": True,
            "tag_combine": "union",
            "tags": ["x"],
        },
    )
    assert resp.status_code == 422


@patch("services.kb_search_service.embed_text")
def test_tag_cooc_disabled_by_feature_flag(
    mock_embed,
    client,
    db_session,
    regular_user,
    jwt_token,
    tmp_path,
):
    mock_embed.return_value = _vec(0.5)
    update_settings(db_session, {KEY_KB_SEARCH_TAG_COOC_ENABLED: "false"})
    db_session.commit()
    invalidate_settings_cache()
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "tagcooc072off"
    seed = _add_source(
        db_session, regular_user.id, tmp_path, "seed.txt", "g" * 32, workspace_id=personal.id
    )
    neighbor = _add_source(
        db_session, regular_user.id, tmp_path, "peer.txt", "h" * 32, workspace_id=personal.id
    )
    replace_file_tags(db_session, regular_user.id, seed.id, ["t1", "t2"])
    replace_file_tags(db_session, regular_user.id, neighbor.id, ["t2"])
    db_session.commit()
    _add_chunk(db_session, regular_user.id, seed.id, f"{query} seed", seed=0.9)
    _add_chunk(db_session, regular_user.id, neighbor.id, f"{query} peer", seed=0.3)

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": query,
            "top_k": 5,
            "file_ids": [seed.id],
            "group_by_file": True,
            "expand_tag_cooc": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body is not None
    assert (body.get("meta") or {}).get("tag_cooc_expanded") is None
    assert {x["file_id"] for x in body["items"]} == {seed.id}


@patch("services.kb_search_service.embed_text")
def test_tag_cooc_more_than_40_tagged_files(
    mock_embed,
    db_session,
    regular_user,
    tmp_path,
):
    """SC-072-007：>40 带标签文件时 cooc 仍正确（不受 UI 图 40 文件限制）。"""
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "tagcooc072bulk"
    seed = _add_source(
        db_session, regular_user.id, tmp_path, "seed.txt", "i" * 32, workspace_id=personal.id
    )
    replace_file_tags(db_session, regular_user.id, seed.id, ["bulk-seed", "bulk-neighbor"])
    twin = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "twin.txt",
        "m" * 32,
        workspace_id=personal.id,
    )
    replace_file_tags(db_session, regular_user.id, twin.id, ["bulk-seed", "bulk-neighbor"])
    db_session.commit()
    _add_chunk(db_session, regular_user.id, seed.id, f"{query} seed", seed=0.95)

    for i in range(45):
        f = _add_source(
            db_session,
            regular_user.id,
            tmp_path,
            f"n{i}.txt",
            f"{i:032d}"[:32],
            workspace_id=personal.id,
        )
        replace_file_tags(db_session, regular_user.id, f.id, ["bulk-neighbor"])
        _add_chunk(db_session, regular_user.id, f.id, f"{query} neighbor {i}", seed=0.2 + i * 0.001)

    primary, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        workspace_id=personal.id,
        file_ids=[seed.id],
        top_k=3,
        group_by_file=True,
    )
    merged, meta = expand_search_items_with_tag_cooc(
        db_session,
        regular_user,
        query,
        primary,
        user_id=regular_user.id,
        search_kwargs={"hybrid": False},
        workspace_id=personal.id,
        cross_workspace=False,
        allowed_file_ids=None,
        top_k=10,
        group_by_file=True,
        min_edge=2,
    )
    assert meta["tag_cooc_expanded"] is True
    assert "bulk-neighbor" in meta["tag_cooc_neighbor_tags"]
    assert len({row["file_id"] for row in merged}) > 1


@patch("services.kb_search_service.embed_text")
def test_tag_cooc_acl_excludes_out_of_scope_file(
    mock_embed,
    db_session,
    regular_user,
    tmp_path,
):
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "tagcooc072acl"
    seed = _add_source(
        db_session, regular_user.id, tmp_path, "seed.txt", "j" * 32, workspace_id=personal.id
    )
    in_scope = _add_source(
        db_session, regular_user.id, tmp_path, "in.txt", "k" * 32, workspace_id=personal.id
    )
    out_scope = _add_source(
        db_session, regular_user.id, tmp_path, "out.txt", "l" * 32, workspace_id=personal.id
    )
    replace_file_tags(db_session, regular_user.id, seed.id, ["acl-a", "acl-b"])
    replace_file_tags(db_session, regular_user.id, in_scope.id, ["acl-b"])
    replace_file_tags(db_session, regular_user.id, out_scope.id, ["acl-b"])
    db_session.commit()
    _add_chunk(db_session, regular_user.id, seed.id, f"{query} seed", seed=0.9)
    _add_chunk(db_session, regular_user.id, in_scope.id, f"{query} in scope", seed=0.4)
    _add_chunk(db_session, regular_user.id, out_scope.id, f"{query} out scope", seed=0.4)

    primary, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        workspace_id=personal.id,
        file_ids=[seed.id],
        top_k=3,
        group_by_file=True,
    )
    allowed = {seed.id, in_scope.id}
    merged, _ = expand_search_items_with_tag_cooc(
        db_session,
        regular_user,
        query,
        primary,
        user_id=regular_user.id,
        search_kwargs={"hybrid": False},
        workspace_id=personal.id,
        cross_workspace=False,
        allowed_file_ids=allowed,
        top_k=5,
        group_by_file=True,
        min_edge=1,
    )
    fids = {row["file_id"] for row in merged}
    assert in_scope.id in fids
    assert out_scope.id not in fids


@patch("services.kb_search_service.embed_text")
def test_tag_cooc_no_semantic_hit_skips_first_chunk_fallback(
    mock_embed,
    db_session,
    regular_user,
    tmp_path,
):
    """FR-B-104：二次 search 无命中时不塞首 chunk（禁止 union 式噪音）。"""
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "tagcooc072noise"
    seed = _add_source(
        db_session, regular_user.id, tmp_path, "seed.txt", "m" * 32, workspace_id=personal.id
    )
    neighbor = _add_source(
        db_session, regular_user.id, tmp_path, "neighbor.txt", "n" * 32, workspace_id=personal.id
    )
    replace_file_tags(db_session, regular_user.id, seed.id, ["alpha", "beta"])
    replace_file_tags(db_session, regular_user.id, neighbor.id, ["beta"])
    db_session.commit()
    _add_chunk(db_session, regular_user.id, seed.id, f"{query} seed chunk", seed=0.9)
    _add_chunk(
        db_session,
        regular_user.id,
        neighbor.id,
        "unrelated boilerplate text without semantic overlap",
        seed=0.05,
    )

    primary, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        workspace_id=personal.id,
        file_ids=[seed.id],
        top_k=3,
        group_by_file=True,
    )

    merged, meta = expand_search_items_with_tag_cooc(
        db_session,
        regular_user,
        query,
        primary,
        user_id=regular_user.id,
        search_kwargs={"hybrid": False},
        workspace_id=personal.id,
        cross_workspace=False,
        allowed_file_ids=None,
        top_k=5,
        group_by_file=True,
        min_edge=1,
    )
    assert meta["tag_cooc_expanded"] is True
    assert meta["tag_cooc_added_hits"] == 0
    assert meta.get("tag_cooc_neighbor_tags")
    fids = {row["file_id"] for row in merged}
    assert neighbor.id not in fids
    assert fids == {seed.id}
