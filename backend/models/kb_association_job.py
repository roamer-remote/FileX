# Copyright (c) 2026 徐泽宇
"""144 durable association extraction jobs."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from database import Base


class KbAssociationJob(Base):
    __tablename__ = "kb_association_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    source_fingerprint = Column(String(64), nullable=False)
    generation = Column(Integer, nullable=False, server_default="0")
    status = Column(String(16), nullable=False, server_default="queued", index=True)
    attempts = Column(Integer, nullable=False, server_default="0")
    last_error = Column(Text, nullable=True)
    worker_id = Column(String(128), nullable=True)
    lease_generation = Column(Integer, nullable=False, server_default="0")
    heartbeat_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
