"""Create kb_multi_repr table for multi-representation index (146 P2).

Revision ID: 0055_kb_multi_repr
Revises: 0053_assoc_reconcile_round
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from config import OLLAMA_EMBED_DIM


revision = "0055_kb_multi_repr"
down_revision = "0053_assoc_reconcile_round"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_multi_repr",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("representation_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(OLLAMA_EMBED_DIM), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_multi_repr_workspace_id", "kb_multi_repr", ["workspace_id"])
    op.create_index("ix_kb_multi_repr_file_id", "kb_multi_repr", ["file_id"])
    op.create_index("ix_kb_multi_repr_type", "kb_multi_repr", ["representation_type"])
    op.create_foreign_key(
        "fk_kb_multi_repr_workspace_id",
        "kb_multi_repr", "workspaces",
        ["workspace_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_kb_multi_repr_file_id",
        "kb_multi_repr", "files",
        ["file_id"], ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_table("kb_multi_repr")
