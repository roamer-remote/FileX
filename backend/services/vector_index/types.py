# Copyright (c) 2026 徐泽宇
"""Vector index DTOs (062)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VectorRecord:
    chunk_id: int
    file_id: int
    workspace_id: int | None
    user_id: int
    embedding: list[float]
    embedding_model: str
    content_kind: str | None = None
