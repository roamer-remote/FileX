"""030 P3: kb_doc_entity_edges for per-document entity graph.

Revision ID: 0016_kb_doc_entity_edges
Revises: 0015_kb_chunk_content_kind
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0016_kb_doc_entity_edges"
down_revision: Union[str, None] = "0015_kb_chunk_content_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_doc_entity_edges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("entity_name", sa.String(length=256), nullable=False),
        sa.Column("entity_type", sa.String(length=32), server_default="concept", nullable=False),
        sa.Column("relation", sa.String(length=64), nullable=True),
        sa.Column("target_entity_name", sa.String(length=256), nullable=True),
        sa.Column("source_chunk_id", sa.BigInteger(), nullable=True),
        sa.Column("provenance", JSONB(), nullable=True),
        sa.Column("extract_layer", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["kb_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_doc_entity_edges_user_id", "kb_doc_entity_edges", ["user_id"])
    op.create_index("ix_kb_doc_entity_edges_workspace_id", "kb_doc_entity_edges", ["workspace_id"])
    op.create_index("ix_kb_doc_entity_edges_file_id", "kb_doc_entity_edges", ["file_id"])
    op.create_index("ix_kb_doc_entity_edges_source_chunk_id", "kb_doc_entity_edges", ["source_chunk_id"])
    op.create_index(
        "ix_kb_doc_entity_edges_file_entity",
        "kb_doc_entity_edges",
        ["file_id", "entity_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_kb_doc_entity_edges_file_entity", table_name="kb_doc_entity_edges")
    op.drop_index("ix_kb_doc_entity_edges_source_chunk_id", table_name="kb_doc_entity_edges")
    op.drop_index("ix_kb_doc_entity_edges_file_id", table_name="kb_doc_entity_edges")
    op.drop_index("ix_kb_doc_entity_edges_workspace_id", table_name="kb_doc_entity_edges")
    op.drop_index("ix_kb_doc_entity_edges_user_id", table_name="kb_doc_entity_edges")
    op.drop_table("kb_doc_entity_edges")
