# Copyright (c) 2026 徐泽宇
"""049 Phase B: external sync sources and item mappings."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database import Base
from models.kb_enums import ExternalSyncDeletePolicy, ExternalSyncItemStatus


class KbExternalSyncSource(Base):
    __tablename__ = "kb_external_sync_sources"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = Column(String(32), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    delete_policy = Column(
        String(32),
        nullable=False,
        server_default=ExternalSyncDeletePolicy.keep_file.value,
    )
    config_public_json = Column(JSONB, nullable=False, server_default="{}")
    secret_ciphertext = Column(LargeBinary, nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class KbExternalSyncItem(Base):
    __tablename__ = "kb_external_sync_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_key", name="uq_external_sync_items"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(
        Integer,
        ForeignKey("kb_external_sync_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_key = Column(String(512), nullable=False)
    external_uri = Column(Text, nullable=True)
    external_updated_at = Column(DateTime(timezone=True), nullable=True)
    file_id = Column(
        Integer,
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_hash = Column(String(64), nullable=True)
    sync_status = Column(
        String(32),
        nullable=False,
        server_default=ExternalSyncItemStatus.active.value,
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
