# Copyright (c) 2026 徐泽宇
"""VectorIndexBackend contract tests (062)."""

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.vector_index import VectorRecord, get_vector_index_backend


def _vec(seed: float) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


def test_pgvector_backend_upsert_search_get_many(db_session, regular_user):
    f = FileModel(
        filename="v.pdf",
        original_name="v.pdf",
        file_path="/tmp/v.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.flush()
    ch = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=0,
        source="main_md",
        text="vector backend test",
        char_start=0,
        char_end=10,
    )
    db_session.add(ch)
    db_session.flush()
    backend = get_vector_index_backend(db_session)
    backend.upsert_many(
        [
            VectorRecord(
                chunk_id=int(ch.id),
                file_id=f.id,
                workspace_id=f.workspace_id,
                user_id=regular_user.id,
                content_kind=None,
                embedding=_vec(0.9),
                embedding_model="test-model",
            )
        ]
    )
    got = backend.get_many([int(ch.id)])
    assert int(ch.id) in got
    assert len(got[int(ch.id)][0]) == OLLAMA_EMBED_DIM
    backend.delete_by_file_id(f.id)
    assert backend.get_many([int(ch.id)]) == {}


def test_search_scored_rows_zero_distance_is_perfect_match(db_session, regular_user):
    """cosine_distance=0 must yield similarity 1.0 (not falsy dist or 1.0)."""
    from sqlalchemy import select
    from models.file import File as FileModel
    from models.kb_chunk import KbChunk

    f = FileModel(
        filename="z.pdf",
        original_name="z.pdf",
        file_path="/tmp/z.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.flush()
    ch = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=0,
        source="main_md",
        text="zero dist",
        char_start=0,
        char_end=9,
    )
    db_session.add(ch)
    db_session.flush()
    vec = _vec(0.42)
    backend = get_vector_index_backend(db_session)
    backend.upsert_many(
        [
            VectorRecord(
                chunk_id=int(ch.id),
                file_id=f.id,
                workspace_id=f.workspace_id,
                user_id=regular_user.id,
                content_kind=None,
                embedding=vec,
                embedding_model="test-model",
            )
        ]
    )
    stmt = select(KbChunk, FileModel).join(FileModel, FileModel.id == KbChunk.file_id).where(KbChunk.id == ch.id)
    scored = backend.search_scored_rows(stmt, vec, fetch_limit=1)
    assert len(scored) == 1
    assert scored[0][2] == 1.0


def test_delete_by_chunk_ids(db_session, regular_user):
    f = FileModel(
        filename="d.pdf",
        original_name="d.pdf",
        file_path="/tmp/d.pdf",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.flush()
    chunks = []
    for i in range(2):
        ch = KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=i,
            source="main_md",
            text=f"chunk {i}",
            char_start=0,
            char_end=7,
        )
        db_session.add(ch)
        db_session.flush()
        chunks.append(ch)
    backend = get_vector_index_backend(db_session)
    backend.upsert_many(
        [
            VectorRecord(
                chunk_id=int(c.id),
                file_id=f.id,
                workspace_id=f.workspace_id,
                user_id=regular_user.id,
                content_kind=None,
                embedding=_vec(0.1 + i),
                embedding_model="test-model",
            )
            for i, c in enumerate(chunks)
        ]
    )
    backend.delete_by_chunk_ids([int(chunks[0].id)])
    got = backend.get_many([int(c.id) for c in chunks])
    assert int(chunks[0].id) not in got
    assert int(chunks[1].id) in got


def test_upsert_many_splits_5304_records_into_batches(monkeypatch):
    from unittest.mock import MagicMock

    from config import OLLAMA_EMBED_DIM
    from services.vector_index.pgvector_backend import PgVectorBackend
    from services.vector_index.types import VectorRecord

    monkeypatch.setattr("services.vector_index.pgvector_backend.KB_VECTOR_UPSERT_BATCH_SIZE", 256)
    db = MagicMock()
    backend = PgVectorBackend(db)
    records = [
        VectorRecord(
            chunk_id=i,
            file_id=1,
            workspace_id=None,
            user_id=1,
            content_kind=None,
            embedding=[0.1] * OLLAMA_EMBED_DIM,
            embedding_model="test-model",
        )
        for i in range(5304)
    ]
    beats: list[int] = []
    backend.upsert_many(records, heartbeat_cb=lambda: beats.append(1))
    assert db.execute.call_count == 21
    assert len(beats) == 21
