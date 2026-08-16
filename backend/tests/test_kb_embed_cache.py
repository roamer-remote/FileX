# Copyright (c) 2026 徐泽宇
"""061 P0-A embed cache tests (SC-061-001～003)."""

import os
from unittest.mock import patch

from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_embedding_cache import KbEmbeddingCache
from models.kb_index_job import KbIndexJob
from services.kb_chunk_ops_service import patch_chunk
from services.kb_chunk_embed_input import build_embed_input, load_file_embed_context
from services.kb_embed_cache_service import hash_embed_input
from services.kb_index_service import JOB_DONE, run_index_job


def _vec(seed: float = 0.01):
    return [seed] * OLLAMA_EMBED_DIM


def _sample_file(db_session, user):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    md_path = os.path.join(UPLOAD_DIR, "cache_test.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# T\n\nAlpha paragraph.\n\nBeta paragraph.")
    f = FileModel(
        filename="c.bin",
        original_name="cache.pdf",
        file_path="/tmp/cache.bin",
        file_size=10,
        mime_type="application/pdf",
        user_id=user.id,
        has_md=True,
        md_file_path=md_path,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
def test_force_reindex_cache_hit_embed_calls_le_one(mock_embed, _notify, db_session, regular_user):
    """SC-061-001: warm cache + force reindex → no extra embed_texts calls."""
    mock_embed.side_effect = lambda texts, **_kwargs: [_vec(0.1 + i * 0.01) for i, _ in enumerate(texts)]
    f = _sample_file(db_session, regular_user)

    job1 = KbIndexJob(user_id=f.user_id, file_id=f.id, force=True)
    db_session.add(job1)
    db_session.commit()
    run_index_job(db_session, job1)
    db_session.commit()
    assert job1.status == JOB_DONE
    first_calls = mock_embed.call_count
    assert first_calls >= 1

    job2 = KbIndexJob(user_id=f.user_id, file_id=f.id, force=True)
    db_session.add(job2)
    db_session.commit()
    run_index_job(db_session, job2)
    db_session.commit()
    assert job2.status == JOB_DONE
    assert mock_embed.call_count == first_calls


@patch("services.kb_embed_cache_service.embed_texts")
def test_patch_chunk_cache_hit_skips_ollama(mock_embed, db_session, regular_user):
    """SC-061-002: patch reembed hits cache when embed input unchanged."""
    mock_embed.return_value = [_vec(0.5)]
    f = FileModel(
        filename="p",
        original_name="p.md",
        file_path="/tmp/p",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    ctx = load_file_embed_context(db_session, f)
    embed_input = build_embed_input(
        body="cached body",
        heading_path="H1",
        workspace_name=ctx.workspace_name,
        tags=ctx.tags,
        content_kind=None,
        original_name=f.original_name,
    )
    h = hash_embed_input(embed_input)
    db_session.add(
        KbEmbeddingCache(
            embed_input_hash=h,
            embedding_model="bge-m3:latest",
            embedding=_vec(0.5),
        )
    )
    db_session.commit()
    ch = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=0,
        source="sidecar_md",
        text="old",
        heading_path="H1",
        char_start=0,
        char_end=3,
        embedding=_vec(0.1),
        embedding_model="test",
    )
    db_session.add(ch)
    db_session.commit()

    patch_chunk(db_session, regular_user, f.id, ch.id, text="cached body", reembed=True)
    mock_embed.assert_not_called()
    db_session.refresh(ch)
    assert list(ch.embedding) == _vec(0.5)


@patch("services.kb_embed_cache_service.enabled", return_value=False)
@patch("services.kb_embed_cache_service.embed_texts")
def test_cache_disabled_matches_direct_embed(mock_embed, _enabled, db_session):
    """SC-061-003: cache disabled → direct embed_texts, no cache rows."""
    from services.kb_embed_cache_service import resolve_embedding_vectors

    mock_embed.return_value = [_vec(0.2), _vec(0.3)]
    texts = ["one", "two"]
    out = resolve_embedding_vectors(db_session, texts)
    assert len(out) == 2
    mock_embed.assert_called_once_with(texts, heartbeat_cb=None, progress_cb=None)
    assert db_session.query(KbEmbeddingCache).count() == 0


def test_hash_embed_input_nfc_normalization():
    import unicodedata

    nfd = "café"
    nfc = unicodedata.normalize("NFC", nfd)
    assert hash_embed_input(nfd) == hash_embed_input(nfc)
