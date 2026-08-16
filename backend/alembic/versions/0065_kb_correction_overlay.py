"""add versioned correction overlays for 187-P2.

Revision ID: 0065_kb_correction_overlay
Revises: 0064_kb_trace_terminal
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0065_kb_correction_overlay"
down_revision: str | None = "0064_kb_trace_terminal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_correction_overlays",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_file_id", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.String(length=128), nullable=False),
        sa.Column("overlay_version", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("parent_version", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=16), server_default="DRAFT", nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_kb_correction_overlay_idempotency"),
        sa.UniqueConstraint(
            "source_file_id", "source_hash", "overlay_version",
            name="uq_kb_correction_overlay_source_version",
        ),
    )
    op.create_index("ix_kb_correction_overlays_source_file_id", "kb_correction_overlays", ["source_file_id"])
    op.create_index("ix_kb_correction_overlays_actor_id", "kb_correction_overlays", ["actor_id"])
    op.create_index("ix_kb_correction_overlays_workspace_id", "kb_correction_overlays", ["workspace_id"])
    op.create_index("ix_kb_correction_overlays_state", "kb_correction_overlays", ["state"])


def downgrade() -> None:
    op.drop_index("ix_kb_correction_overlays_state", table_name="kb_correction_overlays")
    op.drop_index("ix_kb_correction_overlays_workspace_id", table_name="kb_correction_overlays")
    op.drop_index("ix_kb_correction_overlays_actor_id", table_name="kb_correction_overlays")
    op.drop_index("ix_kb_correction_overlays_source_file_id", table_name="kb_correction_overlays")
    op.drop_table("kb_correction_overlays")
