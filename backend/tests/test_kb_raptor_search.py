# Copyright (c) 2026 徐泽宇
"""049 Phase A: RAPTOR search drill-down tests."""

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_raptor_service import RAPTOR_CONTENT_KIND, expand_search_items_with_raptor
from services.kb_search_service import dedupe_search_items_by_chunk_id, search_kb
from services.system_setting_service import (
    KEY_KB_RAPTOR_ENABLED,
    KEY_KB_SEARCH_CACHE_ENABLED,
    KEY_KB_SEARCH_HYBRID_ENABLED,
    invalidate_settings_cache,
    update_settings,
)


def _vec(seed: float = 0.5) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = seed
    return v


def _add_file(db_session, user_id, name: str):
    f = FileModel(
        filename=name,
        original_name=f"{name}.md",
        file_path=f"/tmp/{name}",
        file_size=100,
        mime_type="text/markdown",
        user_id=user_id,
        index_status="ready",
        has_md=True,
    )
    db_session.add(f)
    db_session.commit()
    return f


def _add_chunk(db_session, user_id, file_id, text, *, chunk_index=0, content_kind=None, content_meta=None, seed=0.5):
    row = KbChunk(
        user_id=user_id,
        file_id=file_id,
        chunk_index=chunk_index,
        source="sidecar_md",
        text=text,
        char_start=0,
        char_end=len(text),
        content_kind=content_kind,
        content_meta=content_meta,
        embedding=_vec(seed),
        embedding_model="test",
    )
    db_session.add(row)
    db_session.flush()
    return row


@patch("services.kb_search_service.embed_text")
def test_search_excludes_raptor_when_disabled(mock_embed, db_session, regular_user):
    update_settings(
        db_session,
        {KEY_KB_RAPTOR_ENABLED: "false", KEY_KB_SEARCH_HYBRID_ENABLED: "false"},
    )
    invalidate_settings_cache()
    mock_embed.return_value = _vec(0.9)

    f = _add_file(db_session, regular_user.id, "excl")
    query = "raptorExclSeed"
    base = _add_chunk(db_session, regular_user.id, f.id, f"{query} base chunk", seed=0.4)
    _add_chunk(
        db_session,
        regular_user.id,
        f.id,
        f"{query} summary hit",
        chunk_index=10,
        content_kind=RAPTOR_CONTENT_KIND,
        content_meta={"level": 0, "child_chunk_ids": [int(base.id)]},
        seed=0.95,
    )
    db_session.commit()

    items, _, _, _ = search_kb(db_session, regular_user.id, query, file_ids=[f.id], top_k=5)
    kinds = {it.get("content_kind") for it in items}
    assert RAPTOR_CONTENT_KIND not in kinds


@patch("services.kb_search_service.embed_text")
def test_search_includes_raptor_when_enabled(mock_embed, db_session, regular_user):
    update_settings(
        db_session,
        {KEY_KB_RAPTOR_ENABLED: "true", KEY_KB_SEARCH_HYBRID_ENABLED: "false"},
    )
    invalidate_settings_cache()
    mock_embed.return_value = _vec(0.9)

    f = _add_file(db_session, regular_user.id, "incl")
    query = "raptorInclSeed"
    base = _add_chunk(db_session, regular_user.id, f.id, f"{query} base chunk", seed=0.4)
    summary = _add_chunk(
        db_session,
        regular_user.id,
        f.id,
        f"{query} hierarchical summary",
        chunk_index=10,
        content_kind=RAPTOR_CONTENT_KIND,
        content_meta={"level": 0, "child_chunk_ids": [int(base.id)]},
        seed=0.95,
    )
    db_session.commit()

    items, _, _, _ = search_kb(db_session, regular_user.id, query, file_ids=[f.id], top_k=5)
    chunk_ids = {int(it["chunk_id"]) for it in items if it.get("chunk_id") is not None}
    assert int(summary.id) in chunk_ids


def test_raptor_drilldown_dedupe_shared_child_across_seeds(db_session, regular_user):
    """Major #1: 多种子共享 child 时 drilldown_ids / added_hits 不重复计数。"""
    f = _add_file(db_session, regular_user.id, "shared-child")
    shared = _add_chunk(db_session, regular_user.id, f.id, "shared child text", seed=0.3)
    summary_a = _add_chunk(
        db_session,
        regular_user.id,
        f.id,
        "summary A",
        chunk_index=5,
        content_kind=RAPTOR_CONTENT_KIND,
        content_meta={"level": 1, "child_chunk_ids": [int(shared.id)]},
        seed=0.9,
    )
    summary_b = _add_chunk(
        db_session,
        regular_user.id,
        f.id,
        "summary B",
        chunk_index=6,
        content_kind=RAPTOR_CONTENT_KIND,
        content_meta={"level": 1, "child_chunk_ids": [int(shared.id)]},
        seed=0.85,
    )
    db_session.commit()

    def _seed_hit(summary, score: float) -> dict:
        return {
            "chunk_id": int(summary.id),
            "file_id": f.id,
            "original_name": f.original_name,
            "has_md": True,
            "chunk_index": summary.chunk_index,
            "source": summary.source,
            "text": summary.text,
            "score": score,
            "char_start": 0,
            "char_end": 10,
            "content_kind": RAPTOR_CONTENT_KIND,
            "content_meta": summary.content_meta,
            "matched_chunks": 1,
            "context_text": None,
        }

    primary = [_seed_hit(summary_a, 0.9), _seed_hit(summary_b, 0.85)]
    expanded, meta = expand_search_items_with_raptor(
        db_session,
        primary,
        allowed_file_ids={f.id},
        drill_k=5,
        top_k=5,
        group_by_file=False,
    )
    assert meta["raptor_expanded"] is True
    assert meta["raptor_drilldown_ids"] == [int(shared.id)]
    assert meta["raptor_added_hits"] == 1
    drill_hits = [x for x in expanded if x.get("source_kind") == "raptor_drilldown"]
    assert len(drill_hits) == 1
    assert int(drill_hits[0]["chunk_id"]) == int(shared.id)


def test_raptor_ignores_multi_repr_virtual_chunk_ids(db_session):
    primary = [
        {
            "chunk_id": "repr:14470",
            "content_kind": "multi_repr:raptor_summary",
            "score": 0.9,
        }
    ]

    expanded, meta = expand_search_items_with_raptor(
        db_session,
        primary,
        allowed_file_ids={1},
        drill_k=5,
        top_k=5,
        group_by_file=False,
    )

    assert expanded == primary
    assert meta["raptor_expanded"] is False


def test_raptor_drilldown_dedupe_by_chunk_id(db_session, regular_user):
    f = _add_file(db_session, regular_user.id, "drill")
    child = _add_chunk(db_session, regular_user.id, f.id, "child detail paragraph", seed=0.3)
    summary = _add_chunk(
        db_session,
        regular_user.id,
        f.id,
        "summary overview",
        chunk_index=5,
        content_kind=RAPTOR_CONTENT_KIND,
        content_meta={"level": 0, "child_chunk_ids": [int(child.id)]},
        seed=0.9,
    )
    db_session.commit()

    primary = [
        {
            "chunk_id": int(summary.id),
            "file_id": f.id,
            "original_name": f.original_name,
            "has_md": True,
            "chunk_index": summary.chunk_index,
            "source": summary.source,
            "text": summary.text,
            "score": 0.88,
            "char_start": 0,
            "char_end": 10,
            "content_kind": RAPTOR_CONTENT_KIND,
            "content_meta": summary.content_meta,
            "matched_chunks": 1,
            "context_text": None,
        },
    ]
    expanded, meta = expand_search_items_with_raptor(
        db_session,
        primary,
        allowed_file_ids={f.id},
        drill_k=5,
        score_factor=0.95,
        top_k=5,
        group_by_file=False,
    )
    assert meta["raptor_expanded"] is True
    deduped = dedupe_search_items_by_chunk_id(expanded)
    chunk_ids = [int(x["chunk_id"]) for x in deduped if x.get("chunk_id") is not None]
    assert len(chunk_ids) == len(set(chunk_ids))


def test_raptor_drilldown_appends_child(db_session, regular_user):
    f = _add_file(db_session, regular_user.id, "drill2")
    child = _add_chunk(db_session, regular_user.id, f.id, "child-only-in-drill", seed=0.3)
    summary = _add_chunk(
        db_session,
        regular_user.id,
        f.id,
        "summary-only-in-primary",
        chunk_index=5,
        content_kind=RAPTOR_CONTENT_KIND,
        content_meta={"level": 0, "child_chunk_ids": [int(child.id)]},
        seed=0.9,
    )
    db_session.commit()

    primary = [
        {
            "chunk_id": int(summary.id),
            "file_id": f.id,
            "original_name": f.original_name,
            "has_md": True,
            "chunk_index": summary.chunk_index,
            "source": summary.source,
            "text": summary.text,
            "score": 0.88,
            "char_start": 0,
            "char_end": 10,
            "content_kind": RAPTOR_CONTENT_KIND,
            "content_meta": summary.content_meta,
            "matched_chunks": 1,
            "context_text": None,
        }
    ]
    expanded, meta = expand_search_items_with_raptor(
        db_session,
        primary,
        allowed_file_ids={f.id},
        drill_k=5,
        top_k=5,
        group_by_file=False,
    )
    assert meta["raptor_expanded"] is True
    drill = next(x for x in expanded if int(x["chunk_id"]) == int(child.id))
    assert drill.get("source_kind") == "raptor_drilldown"
    assert float(drill["score"]) == round(0.88 * 0.95, 4)


@patch("services.kb_search_service.embed_text")
def test_raptor_drilldown_respects_acl(mock_embed, db_session, regular_user, admin_user):
    update_settings(db_session, {KEY_KB_RAPTOR_ENABLED: "true", KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    invalidate_settings_cache()
    mock_embed.return_value = _vec(0.9)

    f_allowed = _add_file(db_session, regular_user.id, "acl-ok")
    f_denied = _add_file(db_session, admin_user.id, "acl-no")
    child_ok = _add_chunk(db_session, regular_user.id, f_allowed.id, "allowed child", seed=0.3)
    child_no = _add_chunk(db_session, admin_user.id, f_denied.id, "denied child", seed=0.3)
    summary = _add_chunk(
        db_session,
        regular_user.id,
        f_allowed.id,
        "summary",
        chunk_index=3,
        content_kind=RAPTOR_CONTENT_KIND,
        content_meta={"level": 0, "child_chunk_ids": [int(child_ok.id), int(child_no.id)]},
        seed=0.9,
    )
    db_session.commit()

    primary = [
        {
            "chunk_id": int(summary.id),
            "file_id": f_allowed.id,
            "original_name": f_allowed.original_name,
            "has_md": True,
            "chunk_index": summary.chunk_index,
            "source": summary.source,
            "text": summary.text,
            "score": 0.9,
            "char_start": 0,
            "char_end": 5,
            "content_kind": RAPTOR_CONTENT_KIND,
            "content_meta": summary.content_meta,
            "matched_chunks": 1,
            "context_text": None,
        }
    ]
    expanded, _ = expand_search_items_with_raptor(
        db_session,
        primary,
        allowed_file_ids={f_allowed.id},
        drill_k=5,
        top_k=5,
        group_by_file=False,
    )
    drill_ids = {int(x["chunk_id"]) for x in expanded if x.get("source_kind") == "raptor_drilldown"}
    assert int(child_ok.id) in drill_ids
    assert int(child_no.id) not in drill_ids


@patch("services.kb_search_service.embed_text")
def test_use_query_cache_ignores_raptor_expand(mock_embed, client, db_session, regular_user, jwt_token):
    update_settings(
        db_session,
        {
            KEY_KB_RAPTOR_ENABLED: "true",
            KEY_KB_SEARCH_HYBRID_ENABLED: "false",
            KEY_KB_SEARCH_CACHE_ENABLED: "true",
        },
    )
    invalidate_settings_cache()
    mock_embed.return_value = _vec(0.7)

    f = _add_file(db_session, regular_user.id, "cache")
    query = "raptorCacheSeed"
    child = _add_chunk(db_session, regular_user.id, f.id, f"{query} child", seed=0.3)
    _add_chunk(
        db_session,
        regular_user.id,
        f.id,
        f"{query} summary",
        chunk_index=8,
        content_kind=RAPTOR_CONTENT_KIND,
        content_meta={"level": 0, "child_chunk_ids": [int(child.id)]},
        seed=0.95,
    )
    db_session.commit()

    body = {
        "query": query,
        "top_k": 5,
        "use_query_cache": True,
        "raptor_expand": True,
        "debug": True,
    }
    r1 = client.post("/api/knowledge-base/search", json=body, headers={"Authorization": f"Bearer {jwt_token}"})
    assert r1.status_code == 200
    meta1 = r1.json().get("meta") or {}
    assert meta1.get("raptor_expanded") in (None, False)

    r2 = client.post("/api/knowledge-base/search", json=body, headers={"Authorization": f"Bearer {jwt_token}"})
    assert r2.status_code == 200
    meta2 = r2.json().get("meta") or {}
    assert meta2.get("raptor_expanded") in (None, False)
