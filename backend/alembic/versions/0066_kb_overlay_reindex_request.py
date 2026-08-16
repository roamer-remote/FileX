"""add idempotent index-job linkage for 187-P2 correction reindex.

Revision ID: 0066_kb_overlay_reindex_request
Revises: 0065_kb_correction_overlay
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0066_kb_overlay_reindex_request"
down_revision: str | None = "0065_kb_correction_overlay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kb_index_jobs", sa.Column("correction_overlay_id", sa.Integer(), nullable=True))
    op.add_column("kb_index_jobs", sa.Column("request_key", sa.String(length=256), nullable=True))
    op.create_foreign_key(
        "fk_kb_index_jobs_correction_overlay",
        "kb_index_jobs",
        "kb_correction_overlays",
        ["correction_overlay_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_kb_index_jobs_correction_overlay_id", "kb_index_jobs", ["correction_overlay_id"])
    op.create_index("ix_kb_index_jobs_request_key", "kb_index_jobs", ["request_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_kb_index_jobs_request_key", table_name="kb_index_jobs")
    op.drop_index("ix_kb_index_jobs_correction_overlay_id", table_name="kb_index_jobs")
    op.drop_constraint("fk_kb_index_jobs_correction_overlay", "kb_index_jobs", type_="foreignkey")
    op.drop_column("kb_index_jobs", "request_key")
    op.drop_column("kb_index_jobs", "correction_overlay_id")
