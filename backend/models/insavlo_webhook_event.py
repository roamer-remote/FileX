# Copyright (c) 2026 徐泽宇
"""Insavlo webhook write-back event ORM model."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import func

from database import Base


class InsavloWebhookEvent(Base):
    """Persistent webhook payload event for async write-back and restart recovery."""

    __tablename__ = "insavlo_webhook_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(128), nullable=False, unique=True, index=True)
    job_id = Column(Integer, ForeignKey("kb_extract_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)
    status = Column(String(32), nullable=False, server_default="pending", index=True)
    attempts = Column(Integer, nullable=False, server_default="0")
    last_error = Column(Text, nullable=True)
    received_at = Column(DateTime, nullable=False, server_default=func.now())
    processed_at = Column(DateTime, nullable=True)
