# Copyright (c) 2026 徐泽宇
"""047 T-3: manual override skip + force reindex."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_index_job import KbIndexJob
from services.kb_index_service import (
    JOB_DONE,
    JOB_QUEUED,
    enqueue_index,
    prepare_force_reindex_file,
    run_index_job,
)


def _vec():
    return [0.1] * OLLAMA_EMBED_DIM


@pytest.fixture
def indexed_file_with_override(db_session, regular_user):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, "override_note.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# Title\n\nOriginal md body.\n")
    f = FileModel(
        filename="x.bin",
        original_name="paper.pdf",
        file_path="/tmp/unused.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=md_path,
        index_status="ready",
        index_source_hash="stored-hash",
        chunk_count=1,
        kb_index_manual_override=True,
    )
    db_session.add(f)
    db_session.commit()
    ch = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=0,
        source="sidecar_md",
        text="human edited chunk",
        char_start=0,
        char_end=18,
        embedding=_vec(),
        embedding_model="test",
    )
    db_session.add(ch)
    db_session.commit()
    db_session.refresh(f)
    return f, ch


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
@patch("services.kb_index_service.delete_chunks_for_file")
def test_run_index_job_skips_when_manual_override(
    mock_delete, mock_embed, _mock_notify, db_session, indexed_file_with_override
):
    f, ch = indexed_file_with_override
    job = KbIndexJob(user_id=f.user_id, file_id=f.id, status=JOB_QUEUED, force=False)
    db_session.add(job)
    db_session.commit()

    run_index_job(db_session, job)
    db_session.commit()
    db_session.refresh(f)
    db_session.refresh(ch)
    db_session.refresh(job)

    assert job.status == JOB_DONE
    assert job.last_error is None
    assert f.kb_index_manual_override is True
    assert f.index_source_hash == "stored-hash"
    assert ch.text == "human edited chunk"
    assert f.index_status == "ready"
    mock_delete.assert_not_called()
    mock_embed.assert_not_called()


@patch("services.kb_entity_extract_service.rebuild_doc_entity_edges_for_file")
@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
def test_run_index_job_force_rebuilds_despite_override(
    mock_embed, _mock_notify, _mock_entity, db_session, indexed_file_with_override
):
    mock_embed.side_effect = lambda texts, **_kwargs: [_vec() for _ in texts]
    f, _ch = indexed_file_with_override
    prepare_force_reindex_file(f)
    db_session.commit()
    job = KbIndexJob(user_id=f.user_id, file_id=f.id, status=JOB_QUEUED, force=True)
    db_session.add(job)
    db_session.commit()

    run_index_job(db_session, job)
    db_session.commit()
    db_session.refresh(f)
    db_session.refresh(job)

    assert job.status == JOB_DONE
    assert f.kb_index_manual_override is False
    mock_embed.assert_called()
    chunks = db_session.query(KbChunk).filter(KbChunk.file_id == f.id).all()
    assert len(chunks) >= 1
    texts = {c.text for c in chunks}
    assert "human edited chunk" not in texts
    assert any("Original md body" in t for t in texts)


def test_enqueue_index_sets_job_force(db_session, indexed_file_with_override):
    f, _ = indexed_file_with_override
    job_id = enqueue_index(db_session, f.user_id, f.id, force=True)
    db_session.commit()
    job = db_session.query(KbIndexJob).filter(KbIndexJob.id == job_id).one()
    assert job.force is True


@patch("messaging.kb_index_publisher.publish_kb_index_job")
@patch("services.kb_index_service._notify_file_index")
def test_reindex_api_force_clears_override(
    _mock_notify, _mock_publish, client, jwt_token, db_session, indexed_file_with_override
):
    f, _ = indexed_file_with_override
    r = client.post(
        f"/api/knowledge-base/files/{f.id}/reindex",
        json={"force": True},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    db_session.refresh(f)
    assert f.kb_index_manual_override is False
    assert f.index_source_hash is None
    job = (
        db_session.query(KbIndexJob)
        .filter(KbIndexJob.file_id == f.id)
        .order_by(KbIndexJob.id.desc())
        .first()
    )
    assert job is not None
    assert job.force is True
