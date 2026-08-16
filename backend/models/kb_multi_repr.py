# Copyright (c) 2026 徐泽宇
"""146 P2: Multi-representation index for diverse retrieval entry points.

Stores lightweight text + embedding for alternative representations
(event summaries, entity lists, claim predicates, RAPTOR summaries)
alongside the primary chunk index.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from config import OLLAMA_EMBED_DIM
from database import Base


class KbMultiRepr(Base):
    __tablename__ = "kb_multi_repr"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    representation_type = Column(
        String(32), nullable=False, index=True,
        comment="event_summary | entity_list | claim_predicate | raptor_summary"
    )
    source_id = Column(String(64), nullable=False, comment="来源表的主键 ID")
    text = Column(Text, nullable=False)
    embedding = Column(Vector(OLLAMA_EMBED_DIM), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
