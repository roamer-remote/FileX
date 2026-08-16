"""persist explicit chunk strategy on index jobs for 187-P2.

Revision ID: 0069_kb_index_job_strategy
Revises: 0068_files_source_sha256
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0069_kb_index_job_strategy"
down_revision: str | None = "0068_files_source_sha256"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kb_index_jobs", sa.Column("strategy_id", sa.String(length=32), nullable=True))
    op.add_column("kb_index_jobs", sa.Column("strategy_version", sa.String(length=64), nullable=True))
    op.create_index("ix_kb_index_jobs_strategy_id", "kb_index_jobs", ["strategy_id"])
    op.create_index("ix_kb_index_jobs_strategy_version", "kb_index_jobs", ["strategy_version"])


def downgrade() -> None:
    op.drop_index("ix_kb_index_jobs_strategy_version", table_name="kb_index_jobs")
    op.drop_index("ix_kb_index_jobs_strategy_id", table_name="kb_index_jobs")
    op.drop_column("kb_index_jobs", "strategy_version")
    op.drop_column("kb_index_jobs", "strategy_id")
