# Copyright (c) 2026 徐泽宇
"""kb_chunk_vectors — ANN 向量域（062）。"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, BigInteger
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from config import OLLAMA_EMBED_DIM
from database import Base


class KbChunkVector(Base):
    __tablename__ = "kb_chunk_vectors"

    chunk_id = Column(
        BigInteger,
        ForeignKey("kb_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id = Column(Integer, nullable=False, index=True)
    workspace_id = Column(Integer, nullable=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    content_kind = Column(String(16), nullable=True)
    embedding = Column(Vector(OLLAMA_EMBED_DIM), nullable=False)
    embedding_model = Column(String(64), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
