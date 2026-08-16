# Copyright (c) 2026 徐泽宇
"""PgVectorBackend — kb_chunk_vectors via pgvector (062)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from config import KB_VECTOR_UPSERT_BATCH_SIZE
from models.kb_chunk import KbChunk
from models.kb_chunk_vector import KbChunkVector
from services.vector_index.types import VectorRecord

logger = logging.getLogger(__name__)


class PgVectorBackend:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _upsert_batch(self, records: list[VectorRecord]) -> None:
        """单批 INSERT … ON CONFLICT；不触发 heartbeat（由 upsert_many 外层按批调用 cb）。"""
        payload = [
            {
                "chunk_id": r.chunk_id,
                "file_id": r.file_id,
                "workspace_id": r.workspace_id,
                "user_id": r.user_id,
                "content_kind": r.content_kind,
                "embedding": r.embedding,
                "embedding_model": r.embedding_model,
            }
            for r in records
        ]
        stmt = insert(KbChunkVector).values(payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=["chunk_id"],
            set_={
                "file_id": stmt.excluded.file_id,
                "workspace_id": stmt.excluded.workspace_id,
                "user_id": stmt.excluded.user_id,
                "content_kind": stmt.excluded.content_kind,
                "embedding": stmt.excluded.embedding,
                "embedding_model": stmt.excluded.embedding_model,
            },
        )
        self._db.execute(stmt)

    def upsert_many(
        self,
        records: list[VectorRecord],
        *,
        heartbeat_cb: Callable[[], None] | None = None,
    ) -> None:
        if not records:
            return
        batch_size = KB_VECTOR_UPSERT_BATCH_SIZE
        total_batches = (len(records) + batch_size - 1) // batch_size
        for batch_idx, start in enumerate(range(0, len(records), batch_size), start=1):
            batch = records[start : start + batch_size]
            self._upsert_batch(batch)
            if total_batches > 1:
                logger.info(
                    "kb_vector_upsert_batch batch=%s/%s records=%s",
                    batch_idx,
                    total_batches,
                    len(batch),
                )
            if heartbeat_cb is not None:
                heartbeat_cb()

    def delete_by_file_id(self, file_id: int) -> None:
        self._db.query(KbChunkVector).filter(KbChunkVector.file_id == file_id).delete(
            synchronize_session=False
        )

    def delete_by_chunk_ids(self, chunk_ids: list[int]) -> None:
        if not chunk_ids:
            return
        self._db.query(KbChunkVector).filter(KbChunkVector.chunk_id.in_(chunk_ids)).delete(
            synchronize_session=False
        )

    def search_scored_rows(
        self,
        stmt: Any,
        query_vector: list[float],
        *,
        fetch_limit: int,
    ) -> list[tuple[Any, Any, float]]:
        """JOIN kb_chunk_vectors，按 cosine_distance 升序；第三列为 similarity [0,1]。"""
        dist_expr = KbChunkVector.embedding.cosine_distance(query_vector).label("dist")
        vec_stmt = (
            stmt.join(KbChunkVector, KbChunkVector.chunk_id == KbChunk.id)
            .add_columns(dist_expr)
            .order_by(dist_expr)
            .limit(fetch_limit)
        )
        raw = self._db.execute(vec_stmt).all()
        out: list[tuple[Any, Any, float]] = []
        for chunk, file_row, dist in raw:
            d = 1.0 if dist is None else float(dist)
            sim = max(0.0, 1.0 - d)
            out.append((chunk, file_row, sim))
        return out

    def get_many(self, chunk_ids: list[int]) -> dict[int, tuple[list[float], str]]:
        if not chunk_ids:
            return {}
        rows = (
            self._db.query(KbChunkVector)
            .filter(KbChunkVector.chunk_id.in_(chunk_ids))
            .all()
        )
        return {int(r.chunk_id): (list(r.embedding), r.embedding_model) for r in rows}
