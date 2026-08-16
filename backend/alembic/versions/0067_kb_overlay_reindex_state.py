"""add reindex state to correction overlays for 187-P2.

Revision ID: 0067_kb_overlay_reindex_state
Revises: 0066_kb_overlay_reindex_request
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0067_kb_overlay_reindex_state"
down_revision: str | None = "0066_kb_overlay_reindex_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kb_correction_overlays",
        sa.Column("reindex_status", sa.String(length=16), server_default="NOT_STARTED", nullable=False),
    )
    op.add_column("kb_correction_overlays", sa.Column("reindex_job_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_kb_correction_overlays_reindex_job",
        "kb_correction_overlays",
        "kb_index_jobs",
        ["reindex_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_kb_correction_overlays_reindex_status", "kb_correction_overlays", ["reindex_status"])


def downgrade() -> None:
    op.drop_index("ix_kb_correction_overlays_reindex_status", table_name="kb_correction_overlays")
    op.drop_constraint("fk_kb_correction_overlays_reindex_job", "kb_correction_overlays", type_="foreignkey")
    op.drop_column("kb_correction_overlays", "reindex_job_id")
    op.drop_column("kb_correction_overlays", "reindex_status")
