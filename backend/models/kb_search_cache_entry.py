# Copyright (c) 2026 徐泽宇
"""kb_search_cache_entries ORM model."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

from config import OLLAMA_EMBED_DIM
from database import Base


class KbSearchCacheEntry(Base):
    __tablename__ = "kb_search_cache_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_hash = Column(String(64), nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    query_embedding = Column(Vector(OLLAMA_EMBED_DIM), nullable=False)
    response_payload = Column(JSONB, nullable=False)
    hit_count = Column(Integer, nullable=False, server_default="0")
    last_hit_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
