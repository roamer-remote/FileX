# Copyright (c) 2026 徐泽宇
"""人工修正 overlay 的不可变来源与生命周期模型。"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from database import Base


class KbCorrectionOverlay(Base):
    """A versioned correction overlay kept separate from the original file."""

    __tablename__ = "kb_correction_overlays"
    __table_args__ = (
        UniqueConstraint(
            "source_file_id",
            "source_hash",
            "overlay_version",
            name="uq_kb_correction_overlay_source_version",
        ),
        UniqueConstraint("idempotency_key", name="uq_kb_correction_overlay_idempotency"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    source_hash = Column(String(128), nullable=False)
    overlay_version = Column(Integer, nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    parent_version = Column(Integer, nullable=True)
    state = Column(String(16), nullable=False, server_default="DRAFT", index=True)
    reindex_status = Column(String(16), nullable=False, server_default="NOT_STARTED", index=True)
    reindex_job_id = Column(Integer, ForeignKey("kb_index_jobs.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    activated_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
