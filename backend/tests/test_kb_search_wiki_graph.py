# Copyright (c) 2026 徐泽宇
"""018: search expand_wiki_graph RAG chunk 扩召回。

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
from services.kb_search_wiki_graph import collect_wiki_graph_neighbor_ids, expand_search_items_with_wiki_graph
from services.kb_search_service import TAG_UNION_SCORE, search_kb
from services.system_setting_service import KEY_KB_SEARCH_HYBRID_ENABLED, invalidate_settings_cache, update_settings
from services.workspace_service import ensure_personal_workspace


@pytest.fixture(autouse=True)
def _disable_hybrid(db_session):
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
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


def test_collect_wiki_graph_neighbor_ids_skips_broken(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, tmp_path, "a.txt", "a" * 32, workspace_id=personal.id)
    b = _add_source(db_session, regular_user.id, tmp_path, "b.txt", "b" * 32, workspace_id=personal.id)
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": f"seed [[file:{b.id}]] [[wiki:missing-slug]]\n"},
    )

    neighbors = collect_wiki_graph_neighbor_ids(db_session, regular_user, [a.id])
    assert neighbors == [b.id]


@patch("services.kb_search_wiki_graph.collect_wiki_graph_neighbor_ids")
@patch("services.kb_search_service.embed_text")
def test_expand_wiki_graph_adds_neighbor_chunks(
    mock_embed,
    mock_neighbors,
    db_session,
    regular_user,
    tmp_path,
):
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "wikigraph018seed"
    a = _add_source(
        db_session, regular_user.id, tmp_path, "seed.txt", "a" * 32, workspace_id=personal.id
    )
    b = _add_source(
        db_session, regular_user.id, tmp_path, "neighbor.txt", "b" * 32, workspace_id=personal.id
    )
    mock_neighbors.return_value = [b.id]
    _add_chunk(db_session, regular_user.id, a.id, f"{query} seed chunk", seed=0.9)
    _add_chunk(db_session, regular_user.id, b.id, f"{query} neighbor chunk", seed=0.3)

    primary, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        file_ids=[a.id],
        top_k=3,
        group_by_file=True,
    )
    assert len(primary) == 1 and primary[0]["file_id"] == a.id

    merged, meta = expand_search_items_with_wiki_graph(
        db_session,
        regular_user,
        query,
        primary,
        user_id=regular_user.id,
        search_kwargs={"hybrid": False},
        include_coref=False,
        top_k=3,
        group_by_file=True,
    )
    assert meta["wiki_graph_expanded"] is True
    assert meta["wiki_graph_neighbor_ids"] == [b.id]
    fids = {row["file_id"] for row in merged}
    assert b.id in fids
    neighbor_hit = next(x for x in merged if x["file_id"] == b.id)
    assert neighbor_hit["source_kind"] == "wiki_graph_expand"


@patch("services.kb_search_wiki_graph.collect_wiki_graph_neighbor_ids")
@patch("services.kb_search_service.embed_text")
def test_search_api_expand_wiki_graph(
    mock_embed,
    mock_neighbors,
    client,
    db_session,
    regular_user,
    jwt_token,
    tmp_path,
):
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "wikigraph018api"
    a = _add_source(db_session, regular_user.id, tmp_path, "seed.txt", "c" * 32, workspace_id=personal.id)
    b = _add_source(db_session, regular_user.id, tmp_path, "peer.txt", "d" * 32, workspace_id=personal.id)
    mock_neighbors.return_value = [b.id]
    _add_chunk(db_session, regular_user.id, a.id, f"{query} seed", seed=0.9)
    _add_chunk(db_session, regular_user.id, b.id, f"{query} peer chunk", seed=0.2)

    data = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": query,
            "top_k": 5,
            "group_by_file": True,
            "expand_wiki_graph": True,
            "hybrid": False,
            "debug": True,
        },
    ).json()
    assert data["items"], data
    fids = {x["file_id"] for x in data["items"]}
    assert a.id in fids and b.id in fids
    peer = next(x for x in data["items"] if x["file_id"] == b.id)
    assert peer["source_kind"] == "wiki_graph_expand"
    assert data["meta"]["wiki_graph_expanded"] is True


@patch("services.kb_search_wiki_graph.collect_wiki_graph_neighbor_ids")
@patch("services.kb_search_service.embed_text")
def test_expand_wiki_graph_no_group_by_file(
    mock_embed,
    mock_neighbors,
    db_session,
    regular_user,
    tmp_path,
):
    """group_by_file=False 时不按 file 合并，邻居 chunk 可单独占 top_k 槽位。"""
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "wikigraph018nogroup"
    a = _add_source(
        db_session, regular_user.id, tmp_path, "seed.txt", "e" * 32, workspace_id=personal.id
    )
    b = _add_source(
        db_session, regular_user.id, tmp_path, "neighbor.txt", "f" * 32, workspace_id=personal.id
    )
    mock_neighbors.return_value = [b.id]
    _add_chunk(db_session, regular_user.id, a.id, f"{query} seed chunk", seed=0.9)
    _add_chunk(db_session, regular_user.id, b.id, f"{query} neighbor chunk", seed=0.4)

    primary, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        file_ids=[a.id],
        top_k=2,
        group_by_file=False,
    )
    merged, meta = expand_search_items_with_wiki_graph(
        db_session,
        regular_user,
        query,
        primary,
        user_id=regular_user.id,
        search_kwargs={"hybrid": False},
        include_coref=False,
        top_k=2,
        group_by_file=False,
    )
    assert meta["wiki_graph_added_hits"] >= 1
    assert len(merged) == 2
    assert {row["file_id"] for row in merged} == {a.id, b.id}


@patch("services.kb_search_wiki_graph.search_kb")
@patch("services.kb_search_wiki_graph.collect_wiki_graph_neighbor_ids")
def test_expand_wiki_graph_fallback_when_secondary_empty(
    mock_neighbors,
    mock_search_kb,
    db_session,
    regular_user,
    tmp_path,
):
    """邻居二次 search_kb 无命中时 fallback 到首 chunk。"""
    personal = ensure_personal_workspace(db_session, regular_user)
    a = _add_source(
        db_session, regular_user.id, tmp_path, "seed.txt", "g" * 32, workspace_id=personal.id
    )
    b = _add_source(
        db_session, regular_user.id, tmp_path, "neighbor.txt", "h" * 32, workspace_id=personal.id
    )
    mock_neighbors.return_value = [b.id]
    mock_search_kb.return_value = ([], "test-model", 0, {})
    _add_chunk(db_session, regular_user.id, b.id, "fallback neighbor chunk", seed=0.2)

    primary = [
        {
            "file_id": a.id,
            "score": 0.95,
            "text": "seed",
            "source": "sidecar_md",
            "chunk_index": 0,
        }
    ]
    merged, meta = expand_search_items_with_wiki_graph(
        db_session,
        regular_user,
        "any query",
        primary,
        user_id=regular_user.id,
        search_kwargs={"hybrid": False},
        include_coref=False,
        top_k=3,
        group_by_file=True,
    )
    assert meta["wiki_graph_added_hits"] == 1
    neighbor = next(x for x in merged if x["file_id"] == b.id)
    assert neighbor["source_kind"] == "wiki_graph_expand"
    assert neighbor["score"] == pytest.approx(0.92 * TAG_UNION_SCORE, rel=1e-3)


def test_collect_wiki_graph_neighbor_ids_includes_coref(
    client, db_session, regular_user, jwt_token, tmp_path
):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, tmp_path, "x1.txt", "i" * 32, workspace_id=personal.id)
    b = _add_source(db_session, regular_user.id, tmp_path, "x2.txt", "j" * 32, workspace_id=personal.id)
    for fid in (a.id, b.id):
        client.put(
            f"/api/files/{fid}/md",
            headers=h,
            json={"content": "[[wiki:shared-graph-slug]] peer\n"},
        )

    direct = collect_wiki_graph_neighbor_ids(db_session, regular_user, [a.id], include_coref=False)
    assert b.id not in direct

    with_coref = collect_wiki_graph_neighbor_ids(
        db_session, regular_user, [a.id], include_coref=True
    )
    assert b.id in with_coref

@patch("services.kb_search_wiki_graph.collect_wiki_graph_neighbor_ids")
@patch("services.kb_search_wiki_graph.search_kb")
def test_expand_wiki_graph_with_modality_boost(mock_search_kb, mock_neighbors, db_session, regular_user):
    mock_neighbors.return_value = [99]
    mock_search_kb.return_value = (
        [{"file_id": 99, "chunk_index": 0, "text": "neighbor", "score": 0.4}],
        "test-model",
        3,
        {},
    )
    primary = [{"file_id": 1, "chunk_index": 0, "text": "seed", "score": 0.9}]
    expand_search_items_with_wiki_graph(
        db_session,
        regular_user,
        "示意图",
        primary,
        user_id=regular_user.id,
        search_kwargs={
            "hybrid": False,
            "modality_boost": True,
            "modality_boost_value": 0.25,
        },
        include_coref=False,
        top_k=3,
        group_by_file=True,
    )
    mock_search_kb.assert_called_once()
    assert mock_search_kb.call_args.kwargs["modality_boost"] is True
    assert mock_search_kb.call_args.kwargs["modality_boost_value"] == 0.25

