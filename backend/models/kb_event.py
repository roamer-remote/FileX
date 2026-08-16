# Copyright (c) 2026 徐泽宇
"""077 P0: SAG-style per-chunk events for multi-hop retrieval."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from config import OLLAMA_EMBED_DIM
from database import Base


class KbEvent(Base):
    __tablename__ = "kb_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(
        BigInteger,
        ForeignKey("kb_chunks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    title = Column(String(512), nullable=False)
    summary = Column(Text, nullable=False, server_default="")
    content = Column(Text, nullable=False)
    title_embedding = Column(Vector(OLLAMA_EMBED_DIM), nullable=True)
    extract_layer = Column(String(16), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
