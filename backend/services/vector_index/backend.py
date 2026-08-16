# Copyright (c) 2026 徐泽宇
"""VectorIndexBackend protocol (062)."""

from __future__ import annotations

from typing import Any, Protocol

from collections.abc import Callable
from sqlalchemy.orm import Session

from services.vector_index.types import VectorRecord


class VectorIndexBackend(Protocol):
    def upsert_many(
        self,
        records: list[VectorRecord],
        *,
        heartbeat_cb: Callable[[], None] | None = None,
    ) -> None: ...

    def delete_by_file_id(self, file_id: int) -> None: ...

    def delete_by_chunk_ids(self, chunk_ids: list[int]) -> None: ...

    def search_scored_rows(
        self,
        stmt: Any,
        query_vector: list[float],
        *,
        fetch_limit: int,
    ) -> list[tuple[Any, Any, float]]:
        """pgvector 阶段：对 KbChunk+File 的 Select 做 JOIN 与 cosine ANN。

        返回 (chunk, file, similarity)，similarity = 1 - cosine_distance，范围 [0, 1]。
        """
        ...

    def get_many(self, chunk_ids: list[int]) -> dict[int, tuple[list[float], str]]: ...


def get_vector_index_backend(db: Session) -> VectorIndexBackend:
    from config import KB_VECTOR_BACKEND
    from services.vector_index.pgvector_backend import PgVectorBackend

    backend = (KB_VECTOR_BACKEND or "pgvector").strip().lower()
    if backend == "pgvector":
        return PgVectorBackend(db)
    raise ValueError(f"unknown KB_VECTOR_BACKEND={backend!r}")
