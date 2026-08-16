# Copyright (c) 2026 徐泽宇
"""030 P3: doc entity edges extract + expand_doc_entities."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_doc_entity_edge import KbDocEntityEdge
from services.kb_entity_extract_service import (
    delete_doc_entity_edges_for_file,
    extract_rule_entities,
    rebuild_doc_entity_edges_for_file,
)
from services.kb_search_doc_entity import (
    collect_doc_entity_neighbor_chunk_ids,
    expand_search_items_with_doc_entities,
)
from services.kb_search_service import dedupe_search_items_by_chunk_id, search_kb
from services.kb_search_wiki_graph import expand_search_items_with_wiki_graph
from services.system_setting_service import (
    KEY_KB_SEARCH_HYBRID_ENABLED,
    KEY_KB_SEARCH_MIN_SCORE,
    invalidate_settings_cache,
    update_settings,
)
from services.workspace_service import ensure_personal_workspace


@pytest.fixture(autouse=True)
def _disable_hybrid(db_session):
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    invalidate_settings_cache()
    yield


def _vec(seed: float) -> list[float]:
    """Unit vector with distinct direction per seed (062: avoid collinear ANN ties)."""
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = seed
    v[1] = max(1.0 - abs(seed), 0.05)
    n = (v[0] ** 2 + v[1] ** 2) ** 0.5
    v[0] /= n
    v[1] /= n
    return v


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


def _add_chunk(db_session, user_id, file_id, text, *, chunk_index=0, block_type=None, content_kind=None, content_meta=None, seed=0.5):
    chunk = KbChunk(
        user_id=user_id,
        file_id=file_id,
        chunk_index=chunk_index,
        source="sidecar_md",
        text=text,
        char_start=0,
        char_end=len(text),
        block_type=block_type,
        content_kind=content_kind,
        content_meta=content_meta,
        embedding=_vec(seed),
        embedding_model="test-model",
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    return chunk


def test_extract_rule_entities_table_header(db_session, regular_user, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    f = _add_source(db_session, regular_user.id, tmp_path, "t.md", "a" * 32, workspace_id=personal.id)
    table_text = "| Revenue | Cost |\n| --- | --- |\n| 1 | 2 |"
    chunk = _add_chunk(
        db_session,
        regular_user.id,
        f.id,
        table_text,
        block_type="table",
        content_kind="table",
    )
    edges = extract_rule_entities([chunk])
    names = {e["entity_name"] for e in edges}
    assert "Revenue" in names
    assert "Cost" in names
    assert all(e["extract_layer"] == "rule" for e in edges)


def test_extract_rule_entities_caption(db_session, regular_user, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    f = _add_source(db_session, regular_user.id, tmp_path, "fig.md", "b" * 32, workspace_id=personal.id)
    chunk = _add_chunk(
        db_session,
        regular_user.id,
        f.id,
        "figure body",
        content_kind="figure",
        content_meta={"caption": "Figure 1: Growth curve"},
    )
    edges = extract_rule_entities([chunk])
    assert len(edges) == 1
    assert edges[0]["entity_name"] == "Figure 1: Growth curve"
    assert edges[0]["relation"] == "caption"


@patch("services.kb_entity_extract_service._ollama_chat_json")
def test_llm_extract_disabled_by_default(mock_llm, db_session, regular_user, tmp_path):
    mock_llm.return_value = {"entities": [{"name": "Alpha", "type": "org"}]}
    personal = ensure_personal_workspace(db_session, regular_user)
    f = _add_source(db_session, regular_user.id, tmp_path, "doc.md", "c" * 32, workspace_id=personal.id)
    chunk = _add_chunk(db_session, regular_user.id, f.id, "plain text")
    count = rebuild_doc_entity_edges_for_file(db_session, f)
    db_session.commit()
    mock_llm.assert_not_called()
    assert count >= 0


@patch("services.kb_embed_cache_service.embed_texts")
@patch("services.kb_entity_extract_service._ollama_chat_json")
def test_rebuild_edges_after_index(mock_llm, mock_embed, db_session, regular_user, tmp_path):
    mock_embed.side_effect = lambda texts, **_kwargs: [[0.01] * OLLAMA_EMBED_DIM for _ in texts]
    mock_llm.return_value = None
    from models.kb_index_job import KbIndexJob
    from services.kb_index_service import enqueue_index, publish_index_job, run_index_job

    personal = ensure_personal_workspace(db_session, regular_user)
    f = _add_source(db_session, regular_user.id, tmp_path, "idx.md", "d" * 32, workspace_id=personal.id)
    f.has_md = True
    md_path = tmp_path / "note.md"
    md_path.write_text("| Metric | Value |\n| --- | --- |\n| A | 1 |\n", encoding="utf-8")
    f.md_file_path = str(md_path)
    db_session.commit()

    job_id = enqueue_index(db_session, regular_user.id, f.id)
    db_session.commit()
    publish_index_job(db_session, regular_user.id, f.id, job_id)
    job = db_session.query(KbIndexJob).filter(KbIndexJob.id == job_id).one()
    run_index_job(db_session, job)
    db_session.commit()

    edges = db_session.query(KbDocEntityEdge).filter(KbDocEntityEdge.file_id == f.id).all()
    assert len(edges) >= 2
    assert {e.entity_name for e in edges} >= {"Metric", "Value"}


@patch("services.kb_entity_extract_service._ollama_chat_json")
def test_llm_failure_does_not_block_rebuild(mock_llm, db_session, regular_user, tmp_path):
    mock_llm.side_effect = RuntimeError("ollama down")
    personal = ensure_personal_workspace(db_session, regular_user)
    f = _add_source(db_session, regular_user.id, tmp_path, "fail.md", "e" * 32, workspace_id=personal.id)
    table_text = "| X | Y |\n| --- | --- |\n| 1 | 2 |"
    _add_chunk(db_session, regular_user.id, f.id, table_text, block_type="table")
    count = rebuild_doc_entity_edges_for_file(db_session, f)
    db_session.commit()
    assert count == 2


def test_delete_chunks_removes_edges(db_session, regular_user, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    f = _add_source(db_session, regular_user.id, tmp_path, "del.md", "f" * 32, workspace_id=personal.id)
    chunk = _add_chunk(db_session, regular_user.id, f.id, "| A | B |\n| --- | --- |\n| 1 | 2 |", block_type="table")
    rebuild_doc_entity_edges_for_file(db_session, f)
    db_session.commit()
    assert db_session.query(KbDocEntityEdge).filter(KbDocEntityEdge.file_id == f.id).count() == 2
    delete_doc_entity_edges_for_file(db_session, f.id)
    db_session.commit()
    assert db_session.query(KbDocEntityEdge).filter(KbDocEntityEdge.file_id == f.id).count() == 0
    db_session.delete(chunk)
    db_session.commit()


def test_collect_doc_entity_neighbor_chunk_ids(db_session, regular_user, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    f = _add_source(db_session, regular_user.id, tmp_path, "nei.md", "1" * 32, workspace_id=personal.id)
    c0 = _add_chunk(db_session, regular_user.id, f.id, "seed", chunk_index=0, seed=0.9)
    c1 = _add_chunk(db_session, regular_user.id, f.id, "neighbor", chunk_index=1, seed=0.3)
    db_session.add(
        KbDocEntityEdge(
            user_id=regular_user.id,
            workspace_id=personal.id,
            file_id=f.id,
            entity_name="SharedMetric",
            entity_type="metric",
            relation="column_header",
            source_chunk_id=c0.id,
            extract_layer="rule",
        )
    )
    db_session.add(
        KbDocEntityEdge(
            user_id=regular_user.id,
            workspace_id=personal.id,
            file_id=f.id,
            entity_name="SharedMetric",
            entity_type="metric",
            relation="column_header",
            source_chunk_id=c1.id,
            extract_layer="rule",
        )
    )
    db_session.commit()

    neighbors = collect_doc_entity_neighbor_chunk_ids(
        db_session,
        [c0.id],
        include_coref=True,
        exclude_chunk_ids={c0.id},
    )
    assert c1.id in neighbors


@patch("services.kb_search_service.embed_text")
def test_expand_doc_entities_adds_neighbor(mock_embed, db_session, regular_user, tmp_path):
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "docentity030seed"
    f = _add_source(db_session, regular_user.id, tmp_path, "main.md", "2" * 32, workspace_id=personal.id)
    c0 = _add_chunk(db_session, regular_user.id, f.id, f"{query} seed", chunk_index=0, seed=0.9)
    c1 = _add_chunk(db_session, regular_user.id, f.id, f"{query} neighbor chunk", chunk_index=1, seed=0.3)
    db_session.add(
        KbDocEntityEdge(
            user_id=regular_user.id,
            workspace_id=personal.id,
            file_id=f.id,
            entity_name="LinkEntity",
            entity_type="concept",
            relation="mentions",
            source_chunk_id=c0.id,
            extract_layer="rule",
        )
    )
    db_session.add(
        KbDocEntityEdge(
            user_id=regular_user.id,
            workspace_id=personal.id,
            file_id=f.id,
            entity_name="LinkEntity",
            entity_type="concept",
            relation="mentions",
            source_chunk_id=c1.id,
            extract_layer="rule",
        )
    )
    db_session.commit()

    primary, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        file_ids=[f.id],
        top_k=3,
        group_by_file=False,
    )
    primary = [x for x in primary if int(x["chunk_id"]) == c0.id]
    assert len(primary) == 1
    merged, meta = expand_search_items_with_doc_entities(
        db_session,
        regular_user,
        primary,
        include_coref=True,
        top_k=3,
        group_by_file=False,
    )
    assert meta["doc_entity_expanded"] is True
    chunk_ids = {row.get("chunk_id") for row in merged}
    assert c1.id in chunk_ids
    neighbor = next(x for x in merged if x.get("chunk_id") == c1.id)
    assert neighbor.get("source_kind") == "doc_entity_expand"


@patch("services.kb_search_wiki_graph.collect_wiki_graph_neighbor_ids")
@patch("services.kb_search_service.embed_text")
def test_expand_wiki_and_doc_entity_dedup_chunk_id(
    mock_embed,
    mock_wiki_neighbors,
    db_session,
    regular_user,
    tmp_path,
):
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "dedup030seed"
    f = _add_source(db_session, regular_user.id, tmp_path, "dedup.md", "3" * 32, workspace_id=personal.id)
    c0 = _add_chunk(db_session, regular_user.id, f.id, f"{query} primary", chunk_index=0, seed=0.95)
    c1 = _add_chunk(db_session, regular_user.id, f.id, f"{query} shared neighbor", chunk_index=1, seed=0.4)
    db_session.add(
        KbDocEntityEdge(
            user_id=regular_user.id,
            workspace_id=personal.id,
            file_id=f.id,
            entity_name="Overlap",
            entity_type="concept",
            source_chunk_id=c0.id,
            extract_layer="rule",
        )
    )
    db_session.add(
        KbDocEntityEdge(
            user_id=regular_user.id,
            workspace_id=personal.id,
            file_id=f.id,
            entity_name="Overlap",
            entity_type="concept",
            source_chunk_id=c1.id,
            extract_layer="rule",
        )
    )
    db_session.commit()

    mock_wiki_neighbors.return_value = [f.id]

    primary, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        file_ids=[f.id],
        top_k=5,
        group_by_file=False,
    )
    items, _ = expand_search_items_with_wiki_graph(
        db_session,
        regular_user,
        query,
        primary,
        user_id=regular_user.id,
        search_kwargs={"hybrid": False},
        include_coref=False,
        top_k=5,
        group_by_file=False,
    )
    items, _ = expand_search_items_with_doc_entities(
        db_session,
        regular_user,
        items,
        include_coref=True,
        top_k=5,
        group_by_file=False,
    )
    items = dedupe_search_items_by_chunk_id(items)
    chunk_ids = [int(x["chunk_id"]) for x in items if x.get("chunk_id") is not None]
    assert len(chunk_ids) == len(set(chunk_ids))


def test_dedupe_search_items_by_chunk_id():
    items = [
        {"chunk_id": "repr:7541", "score": 1.0, "source_kind": "multi_repr:raptor_summary"},
        {"chunk_id": 1, "score": 0.9, "source_kind": "search_hit"},
        {"chunk_id": 2, "score": 0.8, "source_kind": "wiki_graph_expand"},
        {"chunk_id": 1, "score": 0.7, "source_kind": "doc_entity_expand"},
    ]
    out = dedupe_search_items_by_chunk_id(items)
    assert [x["chunk_id"] for x in out] == ["repr:7541", 1, 2]
    assert out[1]["source_kind"] == "search_hit"


def test_doc_entity_expansion_ignores_multi_repr_virtual_chunk_ids(db_session, regular_user):
    primary = [{"chunk_id": "repr:7541", "score": 0.9}]

    with patch(
        "services.kb_search_doc_entity.collect_doc_entity_neighbor_chunk_ids",
        return_value=[],
    ):
        expanded, meta = expand_search_items_with_doc_entities(
            db_session,
            regular_user,
            primary,
            include_coref=False,
            top_k=5,
            group_by_file=False,
        )

    assert expanded == primary
    assert meta["doc_entity_expanded"] is False


@patch("services.kb_search_service.embed_text")
def test_search_api_expand_doc_entities(mock_embed, client, db_session, regular_user, jwt_token, tmp_path):
    mock_embed.return_value = _vec(0.9)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "api030entity"
    f = _add_source(db_session, regular_user.id, tmp_path, "api.md", "4" * 32, workspace_id=personal.id)
    c0 = _add_chunk(db_session, regular_user.id, f.id, f"{query} hit", chunk_index=0, seed=0.9)
    c1 = _add_chunk(db_session, regular_user.id, f.id, f"{query} extra", chunk_index=1, seed=0.2)
    for cid in (c0.id, c1.id):
        db_session.add(
            KbDocEntityEdge(
                user_id=regular_user.id,
                workspace_id=personal.id,
                file_id=f.id,
                entity_name="ApiEntity",
                entity_type="concept",
                source_chunk_id=cid,
                extract_layer="rule",
            )
        )
    db_session.commit()

    update_settings(db_session, {KEY_KB_SEARCH_MIN_SCORE: "0.35"})
    invalidate_settings_cache()

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": query,
            "top_k": 5,
            "expand_doc_entities": True,
            "expand_doc_entity_coref": True,
            "debug": True,
            "group_by_file": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["doc_entity_expanded"] is True
    chunk_ids = {item.get("chunk_id") for item in body["items"]}
    assert c1.id in chunk_ids

def test_is_kb_entity_extract_enabled_db_only(db_session, monkeypatch):
    """MAJ-P3-01: config 未强制开启时查 system_settings。"""
    from services.system_setting_service import (
        KEY_KB_ENTITY_EXTRACT_ENABLED,
        invalidate_settings_cache,
        is_kb_entity_extract_enabled,
        update_settings,
    )

    monkeypatch.setattr("config.KB_ENTITY_EXTRACT_ENABLED", False)
    invalidate_settings_cache()
    update_settings(db_session, {KEY_KB_ENTITY_EXTRACT_ENABLED: "true"})
    invalidate_settings_cache()
    assert is_kb_entity_extract_enabled(db_session) is True
    update_settings(db_session, {KEY_KB_ENTITY_EXTRACT_ENABLED: "false"})
    invalidate_settings_cache()
    assert is_kb_entity_extract_enabled(db_session) is False
