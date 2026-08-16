# Copyright (c) 2026 徐泽宇
"""028 module A: KB search query cache."""

from unittest.mock import patch
from types import SimpleNamespace

from config import OLLAMA_EMBED_DIM, OLLAMA_EMBED_MODEL
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_search_cache_entry import KbSearchCacheEntry
from services.kb_search_cache_service import (
    build_scope_hash,
    lookup_query_cache,
    upsert_query_cache,
)
from services.kb_search_service import search_kb
from services.system_setting_service import (
    KEY_KB_SEARCH_CACHE_ENABLED,
    KEY_KB_SEARCH_CACHE_SIMILARITY_THRESHOLD,
    KEY_KB_SEARCH_HYBRID_ENABLED,
    invalidate_settings_cache,
    update_settings,
)
from services.workspace_service import ensure_personal_workspace


def _vec(a: float = 1.0) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = a
    return v


def test_build_scope_hash_stable_for_acl_order():
    h1 = build_scope_hash(
        workspace_id=1,
        allowed_file_ids={3, 1, 2},
        top_k=8,
        file_ids=None,
        tags=["b", "a"],
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
    h2 = build_scope_hash(
        workspace_id=1,
        allowed_file_ids={2, 3, 1},
        top_k=8,
        file_ids=None,
        tags=["a", "b"],
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
    assert h1 == h2


@patch("services.kb_search_service.embed_text")
def test_cache_lookup_hit_updates_last_hit(mock_embed, db_session, regular_user):
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)
    update_settings(
        db_session,
        {
            KEY_KB_SEARCH_HYBRID_ENABLED: "false",
            KEY_KB_SEARCH_CACHE_ENABLED: "true",
            KEY_KB_SEARCH_CACHE_SIMILARITY_THRESHOLD: "0.80",
        },
    )
    invalidate_settings_cache()
    mock_embed.return_value = _vec(0.9)

    scope = build_scope_hash(
        workspace_id=ws.id,
        allowed_file_ids=None,
        top_k=5,
        file_ids=None,
        tags=None,
        tag_mode="or",
        tag_combine="filter",
        hybrid=False,
        filename_boost=False,
        modality_boost=False,
        query_expansion=False,
        include_not_ready=False,
        include_drafts=False,
        group_by_file=False,
        context_chunks=0,
    )
    payload_items = [{"file_id": 1, "text": "cached", "score": 0.9}]
    payload_meta = {"hybrid_enabled": False}
    upsert_query_cache(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        scope_hash=scope,
        query_text="发票报销",
        query_embedding=_vec(0.91),
        items=payload_items,
        meta=payload_meta,
        embedding_model=OLLAMA_EMBED_MODEL,
        top_k=5,
        max_entries_per_user=500,
    )
    db_session.commit()

    hit = lookup_query_cache(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        scope_hash=scope,
        query_embedding=_vec(0.92),
        similarity_threshold=0.80,
        ttl_hours=168,
    )
    assert hit is not None
    assert hit.items[0]["text"] == "cached"
    assert hit.similarity >= 0.80

    row = (
        db_session.query(KbSearchCacheEntry)
        .filter(KbSearchCacheEntry.user_id == regular_user.id)
        .one()
    )
    assert row.hit_count == 1
    assert row.last_hit_at is not None


@patch("services.kb_search_service.embed_text")
def test_search_kb_default_unchanged_without_cache(mock_embed, db_session, regular_user):
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    invalidate_settings_cache()
    mock_embed.return_value = _vec(1.0)

    f = FileModel(
        filename="a",
        original_name="测试资料.pdf",
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
            text="报销流程说明",
            char_start=0,
            char_end=6,
            embedding=_vec(0.9),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    items, _, _, meta = search_kb(db_session, regular_user.id, "报销", top_k=5)
    assert len(items) >= 1
    assert "hybrid_enabled" in meta


def test_search_api_cache_active_still_materializes_allowed(
    monkeypatch,
    client,
    db_session,
    regular_user,
    jwt_token,
):
    ws = ensure_personal_workspace(db_session, regular_user)
    update_settings(
        db_session,
        {
            KEY_KB_SEARCH_HYBRID_ENABLED: "false",
            KEY_KB_SEARCH_CACHE_ENABLED: "true",
            KEY_KB_SEARCH_CACHE_SIMILARITY_THRESHOLD: "0.80",
        },
    )
    invalidate_settings_cache()
    calls = {"accessible": 0}

    def fake_accessible(db, user, workspace_id, *, member=None):
        calls["accessible"] += 1
        assert workspace_id == ws.id
        return {101, 202}

    monkeypatch.setattr(
        "routers.knowledge_base.get_kb_search_cache_settings",
        lambda db: SimpleNamespace(
            enabled=True,
            similarity_threshold=0.80,
            ttl_hours=168,
            max_entries_per_user=500,
        ),
    )
    monkeypatch.setattr("routers.knowledge_base.accessible_file_ids", fake_accessible)
    monkeypatch.setattr("routers.knowledge_base.embed_text", lambda text: _vec(0.9))
    monkeypatch.setattr(
        "routers.knowledge_base.lookup_query_cache",
        lambda *args, **kwargs: SimpleNamespace(
            similarity=0.95,
            entry_id=1,
            items=[
                {
                    "file_id": 101,
                    "original_name": "cached.md",
                    "has_md": True,
                    "chunk_index": 0,
                    "source": "main_md",
                    "text": "cached",
                    "score": 0.9,
                    "char_start": 0,
                    "char_end": 6,
                    "citation_label": "",
                }
            ],
            embedding_model=OLLAMA_EMBED_MODEL,
            top_k=5,
            meta={"hybrid_enabled": False},
        ),
    )

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"query": "cached query", "top_k": 5, "use_query_cache": True},
    )

    assert resp.status_code == 200, resp.text
    assert calls["accessible"] == 1
    payload = resp.json()
    assert payload["meta"]["cache_hit"] is True
    assert payload["items"][0]["file_id"] == 101
