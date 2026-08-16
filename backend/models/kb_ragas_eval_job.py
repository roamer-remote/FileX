# Copyright (c) 2026 徐泽宇
"""Durable PostgreSQL queue model for RAGAS online evaluation."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database import Base


class KbRagasEvalJob(Base):
    """One durable, fenced queue job for one ``KbSearchEval`` row."""

    __tablename__ = "kb_ragas_eval_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    eval_id = Column(
        Integer,
        ForeignKey("kb_search_eval.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status = Column(String(16), nullable=False, server_default="pending", index=True)
    payload_json = Column(JSONB, nullable=False)

    queued_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    worker_id = Column(String(128), nullable=True)
    lease_generation = Column(Integer, nullable=False, server_default="0")
    heartbeat_at = Column(DateTime, nullable=True)
    evaluation_deadline_at = Column(DateTime, nullable=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    attempt_count = Column(Integer, nullable=False, server_default="0")
    failure_stage = Column(String(32), nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
