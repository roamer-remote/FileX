# Copyright (c) 2026 徐泽宇
"""061 P0-C: index pipeline fingerprint skip and rebuild."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_embedding_cache import KbEmbeddingCache
from models.kb_index_job import KbIndexJob
from services.kb_index_fingerprint import (
    compute_index_pipeline_fingerprint,
    describe_fingerprint_field_diff,
    fingerprint_payload,
)
from services.kb_index_service import enqueue_index, run_index_job
from services.system_setting_service import KEY_KB_CHUNK_SIZE, invalidate_settings_cache, update_settings


@pytest.fixture
def sample_file(db_session, regular_user):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, "fp_test.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# Title\n\nAlpha paragraph.\n\nBeta paragraph.")
    f = FileModel(
        filename="fp.bin",
        original_name="fp.md",
        file_path="/tmp/fp.bin",
        file_size=10,
        mime_type="text/markdown",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=md_path,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def _run_index(db_session, sample_file) -> None:
    job_id = enqueue_index(db_session, sample_file.user_id, sample_file.id)
    db_session.commit()
    job = db_session.query(KbIndexJob).filter(KbIndexJob.id == job_id).one()
    run_index_job(db_session, job)
    db_session.commit()
    db_session.refresh(sample_file)


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
def test_fingerprint_skip_on_reindex(mock_embed, _mock_notify, db_session, sample_file):
    mock_embed.side_effect = lambda texts, **_kwargs: [[0.02] * OLLAMA_EMBED_DIM for _ in texts]
    _run_index(db_session, sample_file)
    first_calls = mock_embed.call_count
    assert sample_file.index_pipeline_fingerprint
    _run_index(db_session, sample_file)
    assert mock_embed.call_count == first_calls


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
def test_chunk_size_change_triggers_rebuild(mock_embed, _mock_notify, db_session, sample_file):
    mock_embed.side_effect = lambda texts, **_kwargs: [[0.03] * OLLAMA_EMBED_DIM for _ in texts]
    invalidate_settings_cache()
    update_settings(db_session, {KEY_KB_CHUNK_SIZE: ""})
    _run_index(db_session, sample_file)
    old_fp = sample_file.index_pipeline_fingerprint
    assert old_fp
    invalidate_settings_cache()
    update_settings(db_session, {KEY_KB_CHUNK_SIZE: "300"})
    db_session.query(KbEmbeddingCache).delete()
    calls_after_first = mock_embed.call_count
    _run_index(db_session, sample_file)
    assert sample_file.index_pipeline_fingerprint != old_fp
    assert mock_embed.call_count > calls_after_first


def test_fingerprint_payload_canonical():
    a = compute_index_pipeline_fingerprint(
        text_hash="abc",
        profile_name="long_doc",
        chunk_size=1200,
        chunk_overlap=150,
        embed_header_version=1,
        embedding_model="bge-m3:latest",
    )
    b = compute_index_pipeline_fingerprint(
        **fingerprint_payload(
            text_hash="abc",
            profile_name="long_doc",
            chunk_size=1200,
            chunk_overlap=150,
            embed_header_version=1,
            embedding_model="bge-m3:latest",
        )
    )
    assert a == b



def test_describe_fingerprint_field_diff_old_to_new():
    old = fingerprint_payload(
        text_hash="abc",
        profile_name="long_doc",
        chunk_size=1200,
        chunk_overlap=150,
    )
    new = fingerprint_payload(
        text_hash="abc",
        profile_name="long_doc",
        chunk_size=800,
        chunk_overlap=150,
    )
    diff = describe_fingerprint_field_diff(old, new)
    assert "chunk_size 1200→800" in diff


def test_index_persists_fingerprint_payload(db_session, sample_file):
    with patch("services.kb_index_service._notify_file_index"), patch(
        "services.kb_embed_cache_service.embed_texts",
        side_effect=lambda texts, **_kwargs: [[0.02] * OLLAMA_EMBED_DIM for _ in texts],
    ):
        _run_index(db_session, sample_file)
    assert sample_file.index_fingerprint_payload
    assert "chunk_size" in sample_file.index_fingerprint_payload
    assert sample_file.index_pipeline_fingerprint
