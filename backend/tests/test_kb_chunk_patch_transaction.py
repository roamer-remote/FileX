# Copyright (c) 2026 徐泽宇
"""047 T-5: PATCH chunk 503 rollback + operation_log on success."""

from __future__ import annotations

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.operation_log import OperationLog
from services.kb_ollama_embed import OllamaEmbedError


def _vec():
    return [0.1] * OLLAMA_EMBED_DIM


def _setup(db_session, regular_user, *, override=True):
    f = FileModel(
        filename="a",
        original_name="a.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
        chunk_count=1,
        index_source_hash="keep-hash",
        kb_index_manual_override=override,
    )
    db_session.add(f)
    db_session.commit()
    ch = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=0,
        source="sidecar_md",
        text="before patch",
        char_start=0,
        char_end=12,
        embedding=_vec(),
        embedding_model="test",
    )
    db_session.add(ch)
    db_session.commit()
    db_session.refresh(f)
    db_session.refresh(ch)
    return f, ch


@patch("services.kb_embed_cache_service.embed_texts")
def test_patch_chunk_503_rolls_back_endpoint(mock_embed, client, jwt_token, db_session, regular_user):
    mock_embed.side_effect = OllamaEmbedError("embed down")
    f, ch = _setup(db_session, regular_user)
    embedding_before = list(ch.embedding) if ch.embedding is not None else []
    embedding_model_before = ch.embedding_model
    text_search_before = ch.text_search

    r = client.patch(
        f"/api/knowledge-base/files/{f.id}/chunks/{ch.id}",
        json={"text": "after patch", "reembed": True},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 503

    db_session.expire_all()
    db_session.refresh(ch)
    db_session.refresh(f)
    assert ch.text == "before patch"
    assert list(ch.embedding) if ch.embedding is not None else [] == embedding_before
    assert ch.embedding_model == embedding_model_before
    assert ch.text_search == text_search_before
    assert f.kb_index_manual_override is True
    assert f.index_source_hash == "keep-hash"

    log = (
        db_session.query(OperationLog)
        .filter(OperationLog.action == "kb_chunk_patch", OperationLog.target_id == ch.id)
        .first()
    )
    assert log is None


@patch("services.kb_embed_cache_service.embed_texts")
def test_patch_chunk_success_writes_operation_log(mock_embed, client, jwt_token, db_session, regular_user):
    mock_embed.side_effect = lambda texts, **_kwargs: [_vec() for _ in texts]
    f, ch = _setup(db_session, regular_user, override=False)

    r = client.patch(
        f"/api/knowledge-base/files/{f.id}/chunks/{ch.id}",
        json={"text": "patched", "reembed": True},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200

    log = (
        db_session.query(OperationLog)
        .filter(
            OperationLog.user_id == regular_user.id,
            OperationLog.action == "kb_chunk_patch",
            OperationLog.target_type == "kb_chunk",
            OperationLog.target_id == ch.id,
        )
        .order_by(OperationLog.id.desc())
        .first()
    )
    assert log is not None
    assert f"file_id={f.id}" in (log.detail or "")
    assert "text" in (log.detail or "")


@patch("services.kb_embed_cache_service.embed_texts")
def test_patch_keywords_only_success_logs_without_override(mock_embed, client, jwt_token, db_session, regular_user):
    f, ch = _setup(db_session, regular_user, override=False)

    r = client.patch(
        f"/api/knowledge-base/files/{f.id}/chunks/{ch.id}",
        json={"boost_keywords": "foo, bar", "reembed": False},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    db_session.refresh(f)
    assert f.kb_index_manual_override is False

    log = (
        db_session.query(OperationLog)
        .filter(OperationLog.action == "kb_chunk_patch", OperationLog.target_id == ch.id)
        .first()
    )
    assert log is not None
    mock_embed.assert_not_called()
