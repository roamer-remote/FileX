# Copyright (c) 2026 徐泽宇
"""144: durable, file-scoped facts for global association reasoning."""

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database import Base


class KbEntity(Base):
    """Canonical entity candidate; visibility remains defined by its mentions."""

    __tablename__ = "kb_entities"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(32), nullable=False)
    canonical_name = Column(String(512), nullable=False)
    normalized_name = Column(String(512), nullable=False)
    identity_key = Column(String(512), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index(
            "uq_kb_entities_workspace_type_identity",
            "workspace_id",
            "entity_type",
            "identity_key",
            unique=True,
            postgresql_where=identity_key.isnot(None),
        ),
        Index("ix_kb_entities_workspace_type", "workspace_id", "entity_type"),
        Index("ix_kb_entities_workspace_name", "workspace_id", "entity_type", "normalized_name"),
    )


class KbEntityMention(Base):
    """A file-local entity occurrence and its conservative identity resolution state."""

    __tablename__ = "kb_entity_mentions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(BigInteger, ForeignKey("kb_entities.id", ondelete="SET NULL"), nullable=True, index=True)
    entity_type = Column(String(32), nullable=False)
    surface = Column(String(512), nullable=False)
    normalized_surface = Column(String(512), nullable=False)
    resolution_status = Column(String(16), nullable=False, server_default="unresolved")
    resolution_candidates = Column(JSONB, nullable=True)
    resolution_confidence = Column(Float, nullable=True)
    source_chunk_id = Column(BigInteger, ForeignKey("kb_chunks.id", ondelete="SET NULL"), nullable=True, index=True)
    source_locator = Column(JSONB, nullable=True)
    extract_layer = Column(String(16), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_kb_entity_mentions_file_surface", "file_id", "normalized_surface"),
        Index("ix_kb_entity_mentions_workspace_surface", "workspace_id", "normalized_surface"),
    )


class KbEntityAlias(Base):
    """File-scoped alias evidence; never a standalone authorization source."""

    __tablename__ = "kb_entity_aliases"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entity_id = Column(BigInteger, ForeignKey("kb_entities.id", ondelete="CASCADE"), nullable=False, index=True)
    mention_id = Column(BigInteger, ForeignKey("kb_entity_mentions.id", ondelete="CASCADE"), nullable=False, index=True)
    source_file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    normalized_alias = Column(String(512), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_kb_entity_aliases_entity_alias", "entity_id", "normalized_alias"),)


class KbEvidenceClaim(Base):
    """An extracted, cited assertion between file-local mentions."""

    __tablename__ = "kb_evidence_claims"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_mention_id = Column(BigInteger, ForeignKey("kb_entity_mentions.id", ondelete="CASCADE"), nullable=False, index=True)
    predicate = Column(String(96), nullable=False)
    object_mention_id = Column(BigInteger, ForeignKey("kb_entity_mentions.id", ondelete="CASCADE"), nullable=True, index=True)
    object_value = Column(JSONB, nullable=True)
    qualifiers = Column(JSONB, nullable=True)
    source_chunk_id = Column(BigInteger, ForeignKey("kb_chunks.id", ondelete="SET NULL"), nullable=True, index=True)
    source_locator = Column(JSONB, nullable=True)
    extract_layer = Column(String(16), nullable=True)
    confidence = Column(Float, nullable=True)
    claim_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("uq_kb_evidence_claims_file_hash", "file_id", "claim_hash", unique=True),
        Index("ix_kb_evidence_claims_workspace_predicate", "workspace_id", "predicate"),
    )


class KbAssociationIndexState(Base):
    """Per-file association extraction coverage and retry state."""

    __tablename__ = "kb_association_index_state"

    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    source_fingerprint = Column(String(64), nullable=True)
    extractor_version = Column(String(64), nullable=True)
    content_fingerprint = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, server_default="not_indexed")
    attempt_count = Column(Integer, nullable=False, server_default="0")
    last_error = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
