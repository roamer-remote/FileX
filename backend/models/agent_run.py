# Copyright (c) 2026 徐泽宇
"""107 agent run trace ORM models."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database import Base


def _new_run_id() -> str:
    return str(uuid.uuid4())


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String(36), primary_key=True, default=_new_run_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=True)
    thread_id = Column(String(128), nullable=True, index=True)
    question_preview = Column(String(120), nullable=False, default="")
    intent = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="running")
    started_at = Column(DateTime, nullable=False, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    summary_json = Column(JSONB, nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)


class AgentRunEvent(Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_agent_run_events_run_seq"),
        UniqueConstraint("run_id", "client_event_id", name="uq_agent_run_events_run_client"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(
        String(36),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq = Column(Integer, nullable=False)
    client_event_id = Column(String(36), nullable=True)
    parent_seq = Column(Integer, nullable=True)
    task_key = Column(String(128), nullable=True)
    span_id = Column(String(36), nullable=True)
    attempt = Column(Integer, nullable=False, default=1)
    ts = Column(DateTime, nullable=False, server_default=func.now())
    layer = Column(String(16), nullable=False)
    node_id = Column(String(64), nullable=False)
    label = Column(String(128), nullable=False)
    phase = Column(String(16), nullable=False)
    duration_ms = Column(Integer, nullable=True)
    meta_json = Column(JSONB, nullable=True)
