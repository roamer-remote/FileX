# Copyright (c) 2026 徐泽宇
"""kb_post_jobs ORM model (114 KB post async MQ)."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from database import Base


class KbPostJob(Base):
    __tablename__ = "kb_post_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    index_job_id = Column(Integer, ForeignKey("kb_index_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(16), nullable=False, server_default="queued")
    attempts = Column(Integer, nullable=False, server_default="0")
    oom_retry_count = Column(Integer, nullable=False, server_default="0")
    last_error = Column(Text, nullable=True)
    force = Column(Boolean, nullable=False, server_default="false")
    raptor_only = Column(Boolean, nullable=False, server_default="false")
    force_raptor_settings = Column(Boolean, nullable=False, server_default="false")
    pipeline_fingerprint = Column(String(64), nullable=True)
    post_entity_ms = Column(Integer, nullable=True)
    post_sag_ms = Column(Integer, nullable=True)
    post_raptor_ms = Column(Integer, nullable=True)
    post_skip_reason = Column(String(64), nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
    worker_id = Column(String(128), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    lease_generation = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
