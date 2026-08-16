"""144: durable file-scoped association facts.

Revision ID: 0048_kb_association_facts
Revises: 0047_kb_ragas_eval_queue
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0048_kb_association_facts"
down_revision: Union[str, None] = "0047_kb_ragas_eval_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_entities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("canonical_name", sa.String(length=512), nullable=False),
        sa.Column("normalized_name", sa.String(length=512), nullable=False),
        sa.Column("identity_key", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_entities_workspace_type", "kb_entities", ["workspace_id", "entity_type"])
    op.create_index(
        "ix_kb_entities_workspace_name",
        "kb_entities",
        ["workspace_id", "entity_type", "normalized_name"],
    )
    op.create_index(
        "uq_kb_entities_workspace_type_identity",
        "kb_entities",
        ["workspace_id", "entity_type", "identity_key"],
        unique=True,
        postgresql_where=sa.text("identity_key IS NOT NULL"),
    )
    op.create_table(
        "kb_entity_mentions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("surface", sa.String(length=512), nullable=False),
        sa.Column("normalized_surface", sa.String(length=512), nullable=False),
        sa.Column("resolution_status", sa.String(length=16), server_default="unresolved", nullable=False),
        sa.Column("resolution_candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resolution_confidence", sa.Float(), nullable=True),
        sa.Column("source_chunk_id", sa.BigInteger(), nullable=True),
        sa.Column("source_locator", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extract_layer", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entity_id"], ["kb_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["kb_chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_kb_entity_mentions_user_id", ["user_id"]),
        ("ix_kb_entity_mentions_workspace_id", ["workspace_id"]),
        ("ix_kb_entity_mentions_file_id", ["file_id"]),
        ("ix_kb_entity_mentions_entity_id", ["entity_id"]),
        ("ix_kb_entity_mentions_source_chunk_id", ["source_chunk_id"]),
        ("ix_kb_entity_mentions_file_surface", ["file_id", "normalized_surface"]),
        ("ix_kb_entity_mentions_workspace_surface", ["workspace_id", "normalized_surface"]),
    ):
        op.create_index(name, "kb_entity_mentions", columns)
    op.create_table(
        "kb_entity_aliases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("mention_id", sa.BigInteger(), nullable=False),
        sa.Column("source_file_id", sa.Integer(), nullable=False),
        sa.Column("normalized_alias", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["kb_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mention_id"], ["kb_entity_mentions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_file_id"], ["files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_kb_entity_aliases_entity_id", ["entity_id"]),
        ("ix_kb_entity_aliases_mention_id", ["mention_id"]),
        ("ix_kb_entity_aliases_source_file_id", ["source_file_id"]),
        ("ix_kb_entity_aliases_entity_alias", ["entity_id", "normalized_alias"]),
    ):
        op.create_index(name, "kb_entity_aliases", columns)
    op.create_table(
        "kb_evidence_claims",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("subject_mention_id", sa.BigInteger(), nullable=False),
        sa.Column("predicate", sa.String(length=96), nullable=False),
        sa.Column("object_mention_id", sa.BigInteger(), nullable=True),
        sa.Column("object_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("qualifiers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_chunk_id", sa.BigInteger(), nullable=True),
        sa.Column("source_locator", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extract_layer", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("claim_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_mention_id"], ["kb_entity_mentions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["object_mention_id"], ["kb_entity_mentions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["kb_chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns, unique in (
        ("ix_kb_evidence_claims_user_id", ["user_id"], False),
        ("ix_kb_evidence_claims_workspace_id", ["workspace_id"], False),
        ("ix_kb_evidence_claims_file_id", ["file_id"], False),
        ("ix_kb_evidence_claims_subject_mention_id", ["subject_mention_id"], False),
        ("ix_kb_evidence_claims_object_mention_id", ["object_mention_id"], False),
        ("ix_kb_evidence_claims_source_chunk_id", ["source_chunk_id"], False),
        ("uq_kb_evidence_claims_file_hash", ["file_id", "claim_hash"], True),
        ("ix_kb_evidence_claims_workspace_predicate", ["workspace_id", "predicate"], False),
    ):
        op.create_index(name, "kb_evidence_claims", columns, unique=unique)
    op.create_table(
        "kb_association_index_state",
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="not_indexed", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("file_id"),
    )
    op.create_index("ix_kb_association_index_state_workspace_id", "kb_association_index_state", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_kb_association_index_state_workspace_id", table_name="kb_association_index_state")
    op.drop_table("kb_association_index_state")
    for name in (
        "ix_kb_evidence_claims_workspace_predicate", "uq_kb_evidence_claims_file_hash",
        "ix_kb_evidence_claims_source_chunk_id", "ix_kb_evidence_claims_object_mention_id",
        "ix_kb_evidence_claims_subject_mention_id", "ix_kb_evidence_claims_file_id",
        "ix_kb_evidence_claims_workspace_id", "ix_kb_evidence_claims_user_id",
    ):
        op.drop_index(name, table_name="kb_evidence_claims")
    op.drop_table("kb_evidence_claims")
    for name in (
        "ix_kb_entity_aliases_entity_alias", "ix_kb_entity_aliases_source_file_id",
        "ix_kb_entity_aliases_mention_id", "ix_kb_entity_aliases_entity_id",
    ):
        op.drop_index(name, table_name="kb_entity_aliases")
    op.drop_table("kb_entity_aliases")
    for name in (
        "ix_kb_entity_mentions_workspace_surface", "ix_kb_entity_mentions_file_surface",
        "ix_kb_entity_mentions_source_chunk_id", "ix_kb_entity_mentions_entity_id",
        "ix_kb_entity_mentions_file_id", "ix_kb_entity_mentions_workspace_id",
        "ix_kb_entity_mentions_user_id",
    ):
        op.drop_index(name, table_name="kb_entity_mentions")
    op.drop_table("kb_entity_mentions")
    op.drop_index("uq_kb_entities_workspace_type_identity", table_name="kb_entities")
    op.drop_index("ix_kb_entities_workspace_name", table_name="kb_entities")
    op.drop_index("ix_kb_entities_workspace_type", table_name="kb_entities")
    op.drop_table("kb_entities")
