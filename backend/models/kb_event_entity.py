# Copyright (c) 2026 徐泽宇
"""077 P0: entity bridge rows for SAG event multi-hop retrieval."""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from config import OLLAMA_EMBED_DIM
from database import Base


class KbEventEntity(Base):
    __tablename__ = "kb_event_entities"
    __table_args__ = (
        UniqueConstraint("event_id", "entity_name", name="uq_kb_event_entities_event_entity"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(
        BigInteger,
        ForeignKey("kb_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True
    )
    entity_name = Column(String(256), nullable=False)
    entity_type = Column(String(32), nullable=False, server_default="concept")
    entity_embedding = Column(Vector(OLLAMA_EMBED_DIM), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
