# Copyright (c) 2026 徐泽宇
"""077 P1: SAG multi-hop expand_search_items_with_sag_events + router."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_event import KbEvent
from models.kb_event_entity import KbEventEntity
from models.kb_correction_overlay import KbCorrectionOverlay
from models.kb_index_job import KbIndexJob
from models.operation_log import OperationLog
from models.system_setting import SystemSetting
from models.user import User
from services.kb_sag_search_service import (
    SAG_SCORE_FACTOR,
    expand_search_items_with_sag_events,
    resolve_sag_search_mode,
)
from services.kb_search_service import dedupe_search_items_by_chunk_id, search_kb
from services.system_setting_service import (
    KEY_KB_SEARCH_HYBRID_ENABLED,
    KEY_KB_SEARCH_MIN_SCORE,
    KEY_KB_SAG_QUERY_LLM_ENABLED,
    invalidate_settings_cache,
    update_settings,
)
from services.workspace_service import ensure_personal_workspace
from tests.helpers.kb_chunk_seed import create_kb_chunk


@pytest.fixture(autouse=True)
def _search_defaults(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_SEARCH_HYBRID_ENABLED: "false",
            KEY_KB_SEARCH_MIN_SCORE: "0.35",
            KEY_KB_SAG_QUERY_LLM_ENABLED: "false",
        },
    )
    invalidate_settings_cache()
    yield


def _vec(seed: float) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = seed
    v[1] = max(1.0 - abs(seed), 0.05)
    n = (v[0] ** 2 + v[1] ** 2) ** 0.5
    v[0] /= n
    v[1] /= n
    return v


def _add_source(db_session, user_id, tmp_path, name, md5, **extra):
    path = tmp_path / name
    path.write_text("x", encoding="utf-8")
    file_row = FileModel(
        user_id=user_id,
        filename=name,
        original_name=name,
        file_path=str(path),
        file_size=1,
        mime_type="text/plain",
        md5_hash=md5,
        has_md=False,
        index_status="ready",
        page_kind="source",
        publish_status="published",
        **extra,
    )
    db_session.add(file_row)
    db_session.commit()
    db_session.refresh(file_row)
    return file_row


def _add_chunk(db_session, user_id, file_id, text, *, chunk_index=0, seed=0.5, workspace_id=None):
    chunk = create_kb_chunk(
        db_session,
        user_id=user_id,
        workspace_id=workspace_id,
        file_id=file_id,
        chunk_index=chunk_index,
        source="sidecar_md",
        text=text,
        char_start=0,
        char_end=len(text),
        embedding=_vec(seed),
    )
    db_session.commit()
    db_session.refresh(chunk)
    return chunk


def _add_sag_event(
    db_session,
    *,
    user_id,
    workspace_id,
    file_id,
    chunk,
    title,
    entities: list[tuple[str, str]],
):
    event = KbEvent(
        user_id=user_id,
        workspace_id=workspace_id,
        file_id=file_id,
        chunk_id=int(chunk.id),
        title=title,
        summary=chunk.text[:200],
        content=chunk.text,
        extract_layer="rule",
    )
    db_session.add(event)
    db_session.flush()
    for entity_name, entity_type in entities:
        db_session.add(
            KbEventEntity(
                event_id=int(event.id),
                file_id=file_id,
                workspace_id=workspace_id,
                entity_name=entity_name,
                entity_type=entity_type,
            )
        )
    db_session.commit()
    return event


@patch("services.kb_search_service.embed_text")
def test_multihop_expand_entity_bridge(mock_embed, db_session, regular_user, tmp_path):
    """Synthetic A→event1→BridgeEntity→event2→B multi-hop."""
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "sag077alpha bridge"
    file_row = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "hop.md",
        "a" * 32,
        workspace_id=personal.id,
    )
    chunk_a = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        f"{query} seed chunk",
        chunk_index=0,
        seed=0.95,
        workspace_id=personal.id,
    )
    chunk_b = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        "BridgeEntity sag077beta target chunk",
        chunk_index=1,
        seed=0.35,
        workspace_id=personal.id,
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk_a,
        title="Alpha event",
        entities=[("BridgeEntity", "concept")],
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk_b,
        title="Beta event",
        entities=[("BridgeEntity", "concept"), ("BetaTopic", "concept")],
    )

    primary, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        workspace_id=personal.id,
        file_ids=[file_row.id],
        top_k=3,
        group_by_file=False,
    )
    primary = [row for row in primary if int(row["chunk_id"]) == chunk_a.id]
    assert len(primary) == 1

    merged, meta = expand_search_items_with_sag_events(
        db_session,
        regular_user,
        query,
        primary,
        allowed_file_ids={file_row.id},
        top_k=5,
        group_by_file=False,
        return_search_trace=True,
    )
    assert meta["sag_expanded"] is True
    assert meta["sag_added_hits"] >= 1
    chunk_ids = {int(row["chunk_id"]) for row in merged if row.get("chunk_id") is not None}
    assert chunk_b.id in chunk_ids
    neighbor = next(row for row in merged if int(row["chunk_id"]) == chunk_b.id)
    assert neighbor.get("source_kind") == "sag_event_expand"
    assert float(neighbor["score"]) <= float(primary[0]["score"]) * SAG_SCORE_FACTOR + 0.001
    trace = meta.get("search_trace") or {}
    assert trace.get("seed_event_ids")
    assert trace.get("hop_expanded_event_ids")


def test_sag_ignores_multi_repr_virtual_chunk_ids(db_session, regular_user):
    primary = [
        {
            "chunk_id": "repr:7541",
            "file_id": 1,
            "content_kind": "raptor_summary",
            "score": 0.9,
        }
    ]

    with patch("services.kb_sag_search_service.collect_query_entities", return_value=[]):
        merged, meta = expand_search_items_with_sag_events(
            db_session,
            regular_user,
            "raptor and sag",
            primary,
            allowed_file_ids={1},
            top_k=5,
            group_by_file=False,
        )

    assert merged == primary
    assert meta["sag_expanded"] is False


@patch("services.kb_search_service.embed_text")
def test_acl_no_leak_other_user_file(mock_embed, db_session, regular_user, admin_user, tmp_path):
    mock_embed.return_value = _vec(0.5)
    ws_owner = ensure_personal_workspace(db_session, regular_user)
    ws_other = ensure_personal_workspace(db_session, admin_user)
    query = "sag077acl secret"
    private_file = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "private.md",
        "b" * 32,
        workspace_id=ws_owner.id,
    )
    public_file = _add_source(
        db_session,
        admin_user.id,
        tmp_path,
        "public.md",
        "c" * 32,
        workspace_id=ws_other.id,
    )
    private_chunk = _add_chunk(
        db_session,
        regular_user.id,
        private_file.id,
        f"{query} private seed",
        seed=0.9,
        workspace_id=ws_owner.id,
    )
    secret_chunk = _add_chunk(
        db_session,
        regular_user.id,
        private_file.id,
        "BridgeEntity secret neighbor",
        chunk_index=1,
        seed=0.4,
        workspace_id=ws_owner.id,
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws_owner.id,
        file_id=private_file.id,
        chunk=private_chunk,
        title="Private A",
        entities=[("BridgeEntity", "concept")],
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=ws_owner.id,
        file_id=private_file.id,
        chunk=secret_chunk,
        title="Private B",
        entities=[("BridgeEntity", "concept")],
    )
    admin_chunk = _add_chunk(
        db_session,
        admin_user.id,
        public_file.id,
        f"{query} admin primary",
        seed=0.95,
        workspace_id=ws_other.id,
    )
    _add_sag_event(
        db_session,
        user_id=admin_user.id,
        workspace_id=ws_other.id,
        file_id=public_file.id,
        chunk=admin_chunk,
        title="Admin only",
        entities=[("BridgeEntity", "concept")],
    )

    primary = [
        {
            "chunk_id": admin_chunk.id,
            "file_id": public_file.id,
            "score": 0.9,
            "source_kind": "search_hit",
        }
    ]
    merged, meta = expand_search_items_with_sag_events(
        db_session,
        admin_user,
        query,
        primary,
        allowed_file_ids={public_file.id},
        top_k=5,
        group_by_file=False,
    )
    chunk_ids = {int(row["chunk_id"]) for row in merged if row.get("chunk_id") is not None}
    assert secret_chunk.id not in chunk_ids
    assert meta["sag_neighbor_event_ids"]


def test_standard_degrades_to_fast_when_llm_disabled(db_session):
    effective, requested, degraded = resolve_sag_search_mode(db_session, "standard")
    assert requested == "standard"
    assert effective == "fast"
    assert degraded is True


@patch("services.kb_search_service.embed_text")
def test_return_search_trace_without_debug(mock_embed, client, db_session, regular_user, jwt_token, tmp_path):
    mock_embed.return_value = _vec(0.9)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "sag077trace"
    file_row = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "trace.md",
        "d" * 32,
        workspace_id=personal.id,
    )
    chunk = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        f"{query} trace seed",
        seed=0.9,
        workspace_id=personal.id,
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk,
        title="Trace event",
        entities=[("TraceEntity", "concept")],
    )

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": query,
            "top_k": 5,
            "expand_sag_events": True,
            "return_search_trace": True,
            "debug": False,
            "group_by_file": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"] is not None
    assert body["meta"]["search_trace"] is not None
    assert "timings_ms" in body["meta"]["search_trace"]
    assert "after_acl_filter" in body["meta"]["search_trace"]["counts"]
    assert body["meta"]["search_trace"]["compatibility"]["compatibility_status"] == "unknown"


@patch("services.kb_search_service.embed_text")
def test_readonly_workflow_is_explicit_acl_scoped_and_audited(
    mock_embed, client, db_session, regular_user, jwt_token, tmp_path
):
    mock_embed.return_value = _vec(0.9)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "readonly187primary"
    file_row = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "readonly.md",
        "f" * 32,
        workspace_id=personal.id,
    )
    _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        f"{query} cited evidence",
        seed=0.9,
        workspace_id=personal.id,
    )
    readonly_write_counts = {
        "index_jobs": db_session.query(KbIndexJob).count(),
        "overlays": db_session.query(KbCorrectionOverlay).count(),
        "settings": db_session.query(SystemSetting).count(),
    }

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": query,
            "readonly_workflow_opt_in": True,
            "readonly_workflow_query": "readonly187secondary",
            "top_k": 5,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    workflow = body["meta"]["readonly_workflow"]
    assert workflow["status"] == "COMPLETED"
    assert workflow["receipts"] == 1
    assert workflow["secondary_item_count"] >= 1
    assert body["meta"]["search_trace"] is not None
    assert all(item["file_id"] == file_row.id for item in body["items"])
    assert db_session.query(KbIndexJob).count() == readonly_write_counts["index_jobs"]
    assert db_session.query(KbCorrectionOverlay).count() == readonly_write_counts["overlays"]
    assert db_session.query(SystemSetting).count() == readonly_write_counts["settings"]
    log = (
        db_session.query(OperationLog)
        .filter(OperationLog.action == "kb_readonly_workflow")
        .order_by(OperationLog.id.desc())
        .first()
    )
    assert log is not None
    assert '"status": "COMPLETED"' in log.detail


@patch("services.kb_search_service.embed_text")
def test_readonly_workflow_blocks_without_initial_citation_evidence(
    mock_embed, client, db_session, regular_user, jwt_token
):
    mock_embed.return_value = _vec(0.9)
    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": "readonly187noevidence",
            "readonly_workflow_opt_in": True,
            "readonly_workflow_query": "readonly187secondary",
        },
    )
    assert resp.status_code == 200, resp.text
    workflow = resp.json()["meta"]["readonly_workflow"]
    assert workflow["status"] == "BLOCKED_BY_EVIDENCE"
    assert workflow["receipts"] == 0
    assert workflow["secondary_item_count"] == 0


@patch("services.kb_search_service.embed_text")
def test_readonly_workflow_kill_switch_cancels_before_secondary_search(
    mock_embed, client, db_session, regular_user, jwt_token, tmp_path, monkeypatch
):
    mock_embed.return_value = _vec(0.9)
    personal = ensure_personal_workspace(db_session, regular_user)
    file_row = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "readonly-kill.md",
        "a" * 32,
        workspace_id=personal.id,
    )
    _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        "readonly187kill cited evidence",
        seed=0.9,
        workspace_id=personal.id,
    )
    monkeypatch.setenv("FILEX_KB_READONLY_WORKFLOW_KILL_SWITCH", "true")
    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": "readonly187kill",
            "readonly_workflow_opt_in": True,
            "readonly_workflow_query": "readonly187secondary",
        },
    )
    assert resp.status_code == 200, resp.text
    workflow = resp.json()["meta"]["readonly_workflow"]
    assert workflow["status"] == "CANCELLED"
    assert workflow["secondary_item_count"] == 0


@patch("services.kb_search_service.embed_text")
def test_expand_sag_events_skips_query_cache(mock_embed, client, db_session, regular_user, jwt_token, tmp_path):
    mock_embed.return_value = _vec(0.9)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "sag077cache"
    file_row = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "cache.md",
        "e" * 32,
        workspace_id=personal.id,
    )
    chunk = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        f"{query} cache seed",
        seed=0.9,
        workspace_id=personal.id,
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk,
        title="Cache event",
        entities=[("CacheEntity", "concept")],
    )

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": query,
            "top_k": 5,
            "use_query_cache": True,
            "expand_sag_events": True,
            "debug": True,
            "group_by_file": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["cache_hit"] is False


@patch("services.kb_search_service.embed_text")
def test_dedupe_after_sag_expand(mock_embed, db_session, regular_user, tmp_path):
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "sag077dedupe"
    file_row = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "dedupe.md",
        "f" * 32,
        workspace_id=personal.id,
    )
    chunk = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        f"{query} shared chunk text",
        seed=0.9,
        workspace_id=personal.id,
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk,
        title="Dedupe event",
        entities=[("DedupeEntity", "concept")],
    )
    primary = [
        {
            "chunk_id": chunk.id,
            "file_id": file_row.id,
            "score": 0.9,
            "source_kind": "search_hit",
            "chunk_index": 0,
            "original_name": file_row.original_name,
            "has_md": False,
            "source": "sidecar_md",
            "text": chunk.text,
            "char_start": 0,
            "char_end": len(chunk.text),
            "matched_chunks": 1,
        }
    ]
    merged, meta = expand_search_items_with_sag_events(
        db_session,
        regular_user,
        query,
        primary,
        allowed_file_ids={file_row.id},
        top_k=5,
        group_by_file=False,
    )
    deduped = dedupe_search_items_by_chunk_id(merged)
    assert len(deduped) == 1
    assert meta["sag_expanded"] is True


@patch("services.kb_search_service.embed_text")
def test_sag_does_not_truncate_combined_to_top_k(mock_embed, db_session, regular_user, tmp_path):
    """P1 复审：SAG 阶段不得提前 [:top_k]，保留完整候选供 raptor/dedupe。"""
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "sag077notrunc"
    file_row = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "notrunc.md",
        "g" * 32,
        workspace_id=personal.id,
    )
    chunk_a = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        f"{query} alpha seed",
        chunk_index=0,
        seed=0.95,
        workspace_id=personal.id,
    )
    chunk_b = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        f"{query} beta secondary",
        chunk_index=1,
        seed=0.85,
        workspace_id=personal.id,
    )
    chunk_c = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        "BridgeEntity sag077gamma neighbor",
        chunk_index=2,
        seed=0.35,
        workspace_id=personal.id,
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk_a,
        title="Alpha",
        entities=[("BridgeEntity", "concept")],
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk_c,
        title="Gamma",
        entities=[("BridgeEntity", "concept")],
    )

    primary, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        query,
        workspace_id=personal.id,
        file_ids=[file_row.id],
        top_k=5,
        group_by_file=False,
    )
    primary = [row for row in primary if int(row["chunk_id"]) in {chunk_a.id, chunk_b.id}]
    assert len(primary) >= 2

    merged, meta = expand_search_items_with_sag_events(
        db_session,
        regular_user,
        query,
        primary,
        allowed_file_ids={file_row.id},
        top_k=1,
        group_by_file=False,
    )
    chunk_ids = {int(row["chunk_id"]) for row in merged if row.get("chunk_id") is not None}
    assert chunk_a.id in chunk_ids
    assert chunk_b.id in chunk_ids
    assert chunk_c.id in chunk_ids
    assert len(merged) >= 3
    assert meta["sag_added_hits"] >= 1


@patch("services.kb_search_service.embed_text")
def test_empty_allowed_file_ids_blocks_expand(mock_embed, db_session, regular_user, tmp_path):
    """P1 复审：allowed_file_ids=set() 须保持空 ACL，不得退化为 None 全库扫描。"""
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "sag077emptyacl"
    file_row = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "emptyacl.md",
        "h" * 32,
        workspace_id=personal.id,
    )
    chunk_a = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        f"{query} seed",
        seed=0.9,
        workspace_id=personal.id,
    )
    chunk_b = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        "BridgeEntity neighbor",
        chunk_index=1,
        seed=0.4,
        workspace_id=personal.id,
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk_a,
        title="Seed",
        entities=[("BridgeEntity", "concept")],
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk_b,
        title="Neighbor",
        entities=[("BridgeEntity", "concept")],
    )

    primary = [
        {
            "chunk_id": chunk_a.id,
            "file_id": file_row.id,
            "score": 0.9,
            "source_kind": "search_hit",
            "chunk_index": 0,
            "original_name": file_row.original_name,
            "has_md": False,
            "source": "sidecar_md",
            "text": chunk_a.text,
            "char_start": 0,
            "char_end": len(chunk_a.text),
            "matched_chunks": 1,
        }
    ]
    merged, meta = expand_search_items_with_sag_events(
        db_session,
        regular_user,
        query,
        primary,
        allowed_file_ids=set(),
        top_k=5,
        group_by_file=False,
    )
    assert merged == primary
    assert meta["sag_neighbor_event_ids"] == []
    assert meta["sag_added_hits"] == 0


@patch("services.kb_search_service.embed_text")
def test_api_expand_sag_respects_top_k(mock_embed, client, db_session, regular_user, jwt_token, tmp_path):
    """P1 复评审：路由末端须 group_by_file/top_k 收敛，响应不超过 top_k。"""
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "sag077apitopk"
    file_row = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "apitopk.md",
        "i" * 32,
        workspace_id=personal.id,
    )
    chunk_a = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        f"{query} alpha seed",
        chunk_index=0,
        seed=0.95,
        workspace_id=personal.id,
    )
    _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        f"{query} beta secondary",
        chunk_index=1,
        seed=0.85,
        workspace_id=personal.id,
    )
    chunk_c = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        "BridgeEntity sag077gamma neighbor",
        chunk_index=2,
        seed=0.35,
        workspace_id=personal.id,
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk_a,
        title="Alpha",
        entities=[("BridgeEntity", "concept")],
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk_c,
        title="Gamma",
        entities=[("BridgeEntity", "concept")],
    )

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": query,
            "top_k": 1,
            "expand_sag_events": True,
            "debug": True,
            "group_by_file": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["top_k"] == 1


@patch("services.kb_search_service.embed_text")
def test_api_expand_sag_group_by_file_one_per_file(
    mock_embed, client, db_session, regular_user, jwt_token, tmp_path
):
    """P1 复评审：group_by_file=true 时同一 file_id 最多一条。"""
    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    query = "sag077apigroup"
    file_row = _add_source(
        db_session,
        regular_user.id,
        tmp_path,
        "apigroup.md",
        "j" * 32,
        workspace_id=personal.id,
    )
    chunk_a = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        f"{query} alpha seed",
        chunk_index=0,
        seed=0.95,
        workspace_id=personal.id,
    )
    chunk_c = _add_chunk(
        db_session,
        regular_user.id,
        file_row.id,
        "BridgeEntity sag077gamma neighbor",
        chunk_index=1,
        seed=0.35,
        workspace_id=personal.id,
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk_a,
        title="Alpha",
        entities=[("BridgeEntity", "concept")],
    )
    _add_sag_event(
        db_session,
        user_id=regular_user.id,
        workspace_id=personal.id,
        file_id=file_row.id,
        chunk=chunk_c,
        title="Gamma",
        entities=[("BridgeEntity", "concept")],
    )

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": query,
            "top_k": 5,
            "expand_sag_events": True,
            "debug": True,
            "group_by_file": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    file_ids = [item["file_id"] for item in body["items"]]
    assert len(file_ids) == len(set(file_ids))
    assert file_row.id in file_ids
    assert len([item for item in body["items"] if item["file_id"] == file_row.id]) == 1
