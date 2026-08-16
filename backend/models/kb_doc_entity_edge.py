# Copyright (c) 2026 徐泽宇
"""030 P3: per-document entity edges for expand_doc_entities."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database import Base


class KbDocEntityEdge(Base):
    __tablename__ = "kb_doc_entity_edges"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_name = Column(String(256), nullable=False)
    entity_type = Column(String(32), nullable=False, server_default="concept")
    relation = Column(String(64), nullable=True)
    target_entity_name = Column(String(256), nullable=True)
    source_chunk_id = Column(BigInteger, ForeignKey("kb_chunks.id", ondelete="SET NULL"), nullable=True, index=True)
    provenance = Column(JSONB, nullable=True)
    extract_layer = Column(String(16), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
