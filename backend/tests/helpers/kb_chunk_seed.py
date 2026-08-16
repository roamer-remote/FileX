# Copyright (c) 2026 徐泽宇
"""Test helpers: KbChunk + kb_chunk_vectors (062)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.kb_chunk import KbChunk
from services.vector_index import VectorRecord, get_vector_index_backend


def persist_chunk_with_vector(
    db: Session,
    chunk: KbChunk,
    *,
    embedding: list[float],
    embedding_model: str = "test-model",
) -> KbChunk:
    db.add(chunk)
    db.flush()
    get_vector_index_backend(db).upsert_many(
        [
            VectorRecord(
                chunk_id=int(chunk.id),
                file_id=int(chunk.file_id),
                workspace_id=chunk.workspace_id,
                user_id=int(chunk.user_id),
                content_kind=chunk.content_kind,
                embedding=embedding,
                embedding_model=embedding_model,
            )
        ]
    )
    return chunk


def create_kb_chunk(
    db: Session,
    *,
    embedding: list[float],
    embedding_model: str = "test-model",
    **fields,
) -> KbChunk:
    chunk = KbChunk(**fields)
    return persist_chunk_with_vector(
        db, chunk, embedding=embedding, embedding_model=embedding_model
    )
