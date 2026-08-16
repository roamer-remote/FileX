# Copyright (c) 2026 徐泽宇
"""047 T-4: md 写入清 kb_index_manual_override。"""

from __future__ import annotations

import os
from unittest.mock import patch

from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_index_job import KbIndexJob
from services.kb_index_service import JOB_DONE, JOB_QUEUED, run_index_job
from services.kb_extract_service import persist_extract_markdown
from services.md_note_service import clear_manual_override_on_md_write, save_md_note_for_file
from services.md_paths import md_note_path


def _vec():
    return [0.1] * OLLAMA_EMBED_DIM


def _file_with_override(db_session, regular_user, *, md_body="# Old note\n"):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    f = FileModel(
        filename="a.bin",
        original_name="a.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
        chunk_count=1,
        kb_index_manual_override=True,
    )
    db_session.add(f)
    db_session.commit()
    path = md_note_path(f.id)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(md_body)
    f.has_md = True
    f.md_file_path = path
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
    return f


@patch("services.md_note_service.rebuild_md_note_side_effects")
@patch("services.md_tag_anchor_service.rebuild_anchors_for_file")
def test_save_md_note_clears_manual_override(_anchors, _sidefx, db_session, regular_user):
    f = _file_with_override(db_session, regular_user)
    job_id = save_md_note_for_file(db_session, regular_user.id, f, "# Updated note\n", enqueue_vector_index=True)
    assert job_id is not None
    assert f.kb_index_manual_override is False


@patch("services.md_note_service.rebuild_md_note_side_effects")
@patch("services.md_tag_anchor_service.rebuild_anchors_for_file")
def test_save_md_note_unchanged_keeps_override(_anchors, _sidefx, db_session, regular_user):
    f = _file_with_override(db_session, regular_user, md_body="# Same\n")
    job_id = save_md_note_for_file(db_session, regular_user.id, f, "# Same\n", enqueue_vector_index=True)
    assert job_id is None
    assert f.kb_index_manual_override is True


@patch("services.kb_entity_extract_service.rebuild_doc_entity_edges_for_file")
@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
def test_md_update_allows_index_rebuild(
    mock_embed, _mock_notify, _mock_entity, db_session, regular_user
):
    mock_embed.side_effect = lambda texts, **_kwargs: [_vec() for _ in texts]
    f = _file_with_override(db_session, regular_user)
    with patch("services.md_note_service.rebuild_md_note_side_effects"), patch(
        "services.md_tag_anchor_service.rebuild_anchors_for_file"
    ):
        save_md_note_for_file(db_session, regular_user.id, f, "# Rebuilt from md\n", enqueue_vector_index=False)
    db_session.commit()
    assert f.kb_index_manual_override is False

    job = KbIndexJob(user_id=f.user_id, file_id=f.id, status=JOB_QUEUED, force=False)
    db_session.add(job)
    db_session.commit()
    run_index_job(db_session, job)
    db_session.commit()

    chunks = db_session.query(KbChunk).filter(KbChunk.file_id == f.id).all()
    assert job.status == JOB_DONE
    assert chunks
    assert all(c.text != "human edited chunk" for c in chunks)


@patch("services.md_note_service.rebuild_md_note_side_effects")
@patch("services.md_tag_anchor_service.rebuild_anchors_for_file")
def test_persist_extract_markdown_clears_override(_anchors, _sidefx, db_session, regular_user):
    f = FileModel(
        filename="b.bin",
        original_name="b.pdf",
        file_path="/tmp/b",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        kb_index_manual_override=True,
    )
    db_session.add(f)
    db_session.commit()
    persist_extract_markdown(db_session, f, "# Extracted body\n", engine="test", user_id=regular_user.id)
    assert f.kb_index_manual_override is False
    assert f.has_md is True


def test_clear_manual_override_on_md_write_idempotent(db_session, regular_user):
    f = FileModel(
        filename="c.bin",
        original_name="c.pdf",
        file_path="/tmp/c",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        kb_index_manual_override=True,
    )
    db_session.add(f)
    db_session.commit()
    sample_file = f
    sample_file.kb_index_manual_override = True
    clear_manual_override_on_md_write(sample_file)
    assert sample_file.kb_index_manual_override is False
    clear_manual_override_on_md_write(sample_file)
    assert sample_file.kb_index_manual_override is False
