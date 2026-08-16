# Copyright (c) 2026 徐泽宇
"""kb_embedding_cache ORM model (061 P0-A)."""

from sqlalchemy import BigInteger, Column, DateTime, String, UniqueConstraint, func
from pgvector.sqlalchemy import Vector

from config import OLLAMA_EMBED_DIM
from database import Base


class KbEmbeddingCache(Base):
    __tablename__ = "kb_embedding_cache"
    __table_args__ = (UniqueConstraint("embed_input_hash", "embedding_model"),)


    id = Column(BigInteger, primary_key=True, autoincrement=True)
    embed_input_hash = Column(String(64), nullable=False, index=True)
    embedding_model = Column(String(64), nullable=False)
    embedding = Column(Vector(OLLAMA_EMBED_DIM), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
