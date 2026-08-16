# Copyright (c) 2026 徐泽宇
"""Search disclosure for files that are still being processed."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.system_setting_service import (
    KEY_KB_SEARCH_HYBRID_ENABLED,
    invalidate_settings_cache,
    update_settings,
)
from services.workspace_service import ensure_personal_workspace


@pytest.fixture(autouse=True)
def _disable_hybrid_search_for_processing_hit_tests(db_session):
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    invalidate_settings_cache()
    yield


def _vec(seed: float) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


def _file(db_session, user, *, name: str, index_status: str, **kwargs) -> FileModel:
    ws = ensure_personal_workspace(db_session, user)
    row = FileModel(
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="application/pdf",
        user_id=user.id,
        workspace_id=ws.id,
        index_status=index_status,
        publish_status="published",
        **kwargs,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _chunk(db_session, user, file: FileModel, text: str) -> KbChunk:
    row = KbChunk(
        user_id=user.id,
        workspace_id=file.workspace_id,
        file_id=file.id,
        chunk_index=0,
        source="main_md",
        text=text,
        char_start=0,
        char_end=len(text),
        embedding=_vec(0.2),
        embedding_model="test-model",
    )
    db_session.add(row)
    db_session.commit()
    return row


@patch("services.kb_search_service.embed_text")
def test_search_include_not_ready_returns_processing_placeholder_for_filename_hit(
    mock_embed,
    client,
    db_session,
    regular_user,
    jwt_token,
):
    mock_embed.return_value = _vec(0.5)
    pending = _file(
        db_session,
        regular_user,
        name="北斗协作白皮书.pdf",
        index_status="pending",
        extract_status="processing",
        has_md=False,
    )

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": "北斗协作",
            "top_k": 5,
            "include_not_ready": True,
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["file_id"] == pending.id
    assert item["source_kind"] == "processing_placeholder"
    assert item["is_final"] is False
    assert item["content_confidence"] == "none"
    assert item["processing_stage"] == "extract_processing"
    assert item["text"] == ""
    assert "不可作为正式证据" in item["processing_message"]
    assert data["meta"]["processing_hit_count"] == 1
    assert data["meta"]["processing_file_ids"] == [pending.id]
    assert "处理中资料" in data["agent_notice"]


@patch("services.kb_search_service.embed_text")
def test_search_preserves_processing_placeholder_when_ready_hits_fill_top_k(
    mock_embed,
    client,
    db_session,
    regular_user,
    jwt_token,
):
    mock_embed.return_value = _vec(0.5)
    ready = _file(
        db_session,
        regular_user,
        name="ready-hit.pdf",
        index_status="ready",
        extract_status="ready",
        has_md=True,
    )
    pending = _file(
        db_session,
        regular_user,
        name="北斗协作白皮书.pdf",
        index_status="pending",
        extract_status="processing",
        has_md=False,
    )
    _chunk(db_session, regular_user, ready, "北斗协作 ready hit")

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": "北斗协作",
            "top_k": 1,
            "include_not_ready": True,
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["file_id"] == pending.id
    assert data["items"][0]["source_kind"] == "processing_placeholder"
    assert data["items"][0]["text"] == ""
    assert data["meta"]["processing_hit_count"] == 1
    assert data["meta"]["processing_file_ids"] == [pending.id]


@patch("services.kb_search_service.embed_text")
def test_search_default_excludes_processing_placeholder_for_not_ready_file(
    mock_embed,
    client,
    db_session,
    regular_user,
    jwt_token,
):
    mock_embed.return_value = _vec(0.5)
    _file(
        db_session,
        regular_user,
        name="北斗协作白皮书.pdf",
        index_status="pending",
        extract_status="processing",
        has_md=False,
    )

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"query": "北斗协作", "top_k": 5, "debug": True},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items"] == []
    assert data["meta"]["processing_hit_count"] == 0
    assert data["meta"]["processing_file_ids"] == []


@patch("services.kb_search_service.embed_text")
def test_search_include_not_ready_does_not_leak_stale_chunk_text(
    mock_embed,
    client,
    db_session,
    regular_user,
    jwt_token,
):
    mock_embed.return_value = _vec(0.5)
    pending = _file(
        db_session,
        regular_user,
        name="北斗协作旧索引.pdf",
        index_status="pending",
        extract_status="processing",
        has_md=False,
    )
    _chunk(db_session, regular_user, pending, "北斗协作 stale chunk should not leak")

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": "北斗协作",
            "top_k": 5,
            "include_not_ready": True,
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["file_id"] == pending.id
    assert item["source_kind"] == "processing_placeholder"
    assert item["text"] == ""
    assert "stale chunk" not in str(item)


@patch("services.kb_search_service.embed_text")
def test_search_ready_hit_discloses_post_processing_status(
    mock_embed,
    client,
    db_session,
    regular_user,
    jwt_token,
):
    mock_embed.return_value = _vec(0.5)
    running = _file(
        db_session,
        regular_user,
        name="running-post.pdf",
        index_status="ready",
        extract_status="ready",
        kb_post_status="running",
        has_md=True,
    )
    failed = _file(
        db_session,
        regular_user,
        name="failed-post.pdf",
        index_status="ready",
        extract_status="ready",
        kb_post_status="failed",
        kb_post_error="raptor timeout",
        has_md=True,
    )
    _chunk(db_session, regular_user, running, "北斗协作 正在后处理")
    _chunk(db_session, regular_user, failed, "北斗协作 后处理失败")

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"query": "北斗协作", "top_k": 5, "debug": True},
    )

    assert resp.status_code == 200, resp.text
    by_file = {item["file_id"]: item for item in resp.json()["items"]}
    assert by_file[running.id]["source_kind"] == "final_md_post_pending"
    assert by_file[running.id]["is_final"] is True
    assert by_file[running.id]["content_confidence"] == "partial"
    assert by_file[running.id]["processing_stage"] == "post_running"
    assert "后处理仍在进行" in by_file[running.id]["processing_message"]
    assert by_file[failed.id]["source_kind"] == "final_md_post_failed"
    assert by_file[failed.id]["is_final"] is True
    assert by_file[failed.id]["content_confidence"] == "partial"
    assert by_file[failed.id]["processing_stage"] == "post_failed"
    assert "高级后处理失败" in by_file[failed.id]["processing_message"]
