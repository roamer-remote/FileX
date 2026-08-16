# Copyright (c) 2026 徐泽宇
"""084: KB index/search workspace ACL alignment."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM, OLLAMA_EMBED_MODEL
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_index_job import KbIndexJob
from services.auth_service import create_access_token
from services.kb_index_service import run_index_job
from services.kb_search_cache_service import build_scope_hash, lookup_query_cache, upsert_query_cache
from services.kb_search_wiki_graph import collect_wiki_graph_neighbor_ids
from services.system_setting_service import (
    KEY_KB_SEARCH_CACHE_ENABLED,
    KEY_KB_SEARCH_HYBRID_ENABLED,
    KEY_SHARED_WORKSPACES_ENABLED,
    invalidate_settings_cache,
    update_settings,
)
from services.vector_index import get_vector_index_backend
from services.workspace_service import create_shared_workspace, ensure_personal_workspace, set_member_role
from tests.conftest import _create_user


@pytest.fixture(autouse=True)
def _kb_acl_defaults(db_session):
    update_settings(
        db_session,
        {
            KEY_SHARED_WORKSPACES_ENABLED: "true",
            KEY_KB_SEARCH_HYBRID_ENABLED: "false",
            KEY_KB_SEARCH_CACHE_ENABLED: "false",
        },
    )
    invalidate_settings_cache()
    yield


def _vec(seed: float = 0.5) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


def _auth(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.password_rev)}"}


def _ready_file(db_session, owner, workspace_id: int, name: str) -> FileModel:
    md5_seed = (name.replace(".", "") or "file")[:16]
    f = FileModel(
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="text/markdown",
        md5_hash=(md5_seed * 32)[:32],
        user_id=owner.id,
        workspace_id=workspace_id,
        has_md=True,
        index_status="ready",
        publish_status="published",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def _chunk(db_session, owner, file: FileModel, text: str, seed: float = 0.5) -> KbChunk:
    c = KbChunk(
        user_id=owner.id,
        workspace_id=file.workspace_id,
        file_id=file.id,
        chunk_index=0,
        source="sidecar_md",
        text=text,
        char_start=0,
        char_end=len(text),
        embedding=_vec(seed),
        embedding_model="test-model",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@patch("services.kb_raptor_service.maybe_build_raptor_tree")
@patch("services.kb_embed_cache_service.embed_texts")
@patch("services.kb_index_service.resolve_index_text")
def test_index_job_persists_chunks_and_vectors_in_file_workspace(
    mock_resolve,
    mock_embed,
    _mock_raptor,
    db_session,
    regular_user,
    tmp_path,
):
    shared = create_shared_workspace(db_session, name="084-index-ws", owner=regular_user)
    source_path = tmp_path / "acl-index.md"
    source_path.write_text("# ACL Index\n\nworkspace chunk alignment", encoding="utf-8")
    mock_resolve.return_value = (source_path.read_text(encoding="utf-8"), "sidecar_md")
    mock_embed.side_effect = lambda texts, **_kwargs: [_vec(0.7) for _ in texts]

    f = FileModel(
        filename="acl-index.md",
        original_name="acl-index.md",
        file_path=str(source_path),
        file_size=source_path.stat().st_size,
        mime_type="text/markdown",
        user_id=regular_user.id,
        workspace_id=shared.id,
        has_md=True,
        md_file_path=str(source_path),
        index_status="pending",
    )
    db_session.add(f)
    db_session.commit()

    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="queued")
    db_session.add(job)
    db_session.commit()

    run_index_job(db_session, job)

    chunks = db_session.query(KbChunk).filter(KbChunk.file_id == f.id).all()
    assert job.status == "done", job.last_error
    assert chunks
    assert {c.workspace_id for c in chunks} == {shared.id}

    vectors = get_vector_index_backend(db_session).get_many([int(c.id) for c in chunks])
    assert set(vectors) == {int(c.id) for c in chunks}


@patch("services.kb_search_service.embed_text")
def test_single_workspace_search_requires_membership_and_uses_workspace_acl(
    mock_embed,
    client,
    db_session,
    regular_user,
):
    mock_embed.return_value = _vec(0.6)
    member = _create_user(db_session, "acl084_member")
    outsider = _create_user(db_session, "acl084_outsider")
    shared = create_shared_workspace(db_session, name="084-shared-search", owner=regular_user)
    set_member_role(db_session, shared.id, member.id, "viewer")
    f = _ready_file(db_session, regular_user, shared.id, "member-visible.md")
    _chunk(db_session, regular_user, f, "workspace acl member visible", seed=0.6)

    ok = client.post(
        "/api/knowledge-base/search",
        headers=_auth(member),
        params={"workspace_id": shared.id},
        json={"query": "workspace acl", "top_k": 5, "hybrid": False},
    )
    assert ok.status_code == 200, ok.text
    assert f.id in {item["file_id"] for item in ok.json()["items"]}

    denied = client.post(
        "/api/knowledge-base/search",
        headers=_auth(outsider),
        params={"workspace_id": shared.id},
        json={"query": "workspace acl", "top_k": 5, "hybrid": False},
    )
    assert denied.status_code == 403, denied.text


@patch("services.kb_search_service.embed_text")
def test_cross_workspace_search_excludes_workspaces_without_membership(
    mock_embed,
    client,
    db_session,
    regular_user,
):
    mock_embed.return_value = _vec(0.6)
    searcher = _create_user(db_session, "acl084_searcher")
    personal = ensure_personal_workspace(db_session, searcher)
    shared = create_shared_workspace(db_session, name="084-hidden-shared", owner=regular_user)

    personal_file = _ready_file(db_session, searcher, personal.id, "personal-visible.md")
    hidden_file = _ready_file(db_session, regular_user, shared.id, "shared-hidden.md")
    _chunk(db_session, searcher, personal_file, "cross workspace own visible", seed=0.6)
    _chunk(db_session, regular_user, hidden_file, "cross workspace hidden shared", seed=0.6)

    resp = client.post(
        "/api/knowledge-base/search",
        headers=_auth(searcher),
        params={"cross_workspace": True},
        json={"query": "cross workspace", "top_k": 10, "hybrid": False},
    )
    assert resp.status_code == 200, resp.text
    hit_ids = {item["file_id"] for item in resp.json()["items"]}
    assert personal_file.id in hit_ids
    assert hidden_file.id not in hit_ids


def test_wiki_graph_neighbors_exclude_acl_invisible_targets(
    client,
    db_session,
    regular_user,
):
    member = _create_user(db_session, "acl084_graph_member")
    private_ws = ensure_personal_workspace(db_session, regular_user)
    shared = create_shared_workspace(db_session, name="084-graph-shared", owner=regular_user)
    set_member_role(db_session, shared.id, member.id, "viewer")

    seed = _ready_file(db_session, regular_user, shared.id, "graph-seed.md")
    visible = _ready_file(db_session, regular_user, shared.id, "graph-visible.md")
    hidden = _ready_file(db_session, regular_user, private_ws.id, "graph-hidden.md")

    resp = client.put(
        f"/api/files/{seed.id}/md",
        headers=_auth(regular_user),
        params={"workspace_id": shared.id},
        json={"content": f"[[file:{visible.id}]] [[file:{hidden.id}]]"},
    )
    assert resp.status_code == 200, resp.text

    neighbors = collect_wiki_graph_neighbor_ids(db_session, member, [seed.id])
    assert visible.id in neighbors
    assert hidden.id not in neighbors


def test_query_cache_scope_changes_when_allowed_file_ids_change(db_session, regular_user):
    ws = ensure_personal_workspace(db_session, regular_user)
    scope_before = build_scope_hash(
        workspace_id=ws.id,
        allowed_file_ids={1, 2},
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
    scope_after = build_scope_hash(
        workspace_id=ws.id,
        allowed_file_ids={1},
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
    assert scope_before != scope_after

    upsert_query_cache(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        scope_hash=scope_before,
        query_text="acl cache",
        query_embedding=_vec(0.8),
        items=[{"file_id": 2, "text": "cached hidden", "score": 0.9}],
        meta={"hybrid_enabled": False},
        embedding_model=OLLAMA_EMBED_MODEL,
        top_k=5,
        max_entries_per_user=500,
    )
    db_session.commit()

    stale_hit = lookup_query_cache(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws.id,
        scope_hash=scope_after,
        query_embedding=_vec(0.8),
        similarity_threshold=0.5,
        ttl_hours=168,
    )
    assert stale_hit is None
