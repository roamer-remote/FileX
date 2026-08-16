"""gpu scheduler observability state (164 §9).

Revision ID: 0061
Revises: 0060_gpu_oom_retry_count
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0061_gpu_scheduler_state"
down_revision: str | None = "0060_gpu_oom_retry_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gpu_scheduler_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_group", sa.String(length=16), nullable=False, server_default="none"),
        sa.Column("model_status", sa.String(length=32), nullable=False, server_default="unloaded"),
        sa.Column("switch_started_at", sa.DateTime(), nullable=True),
        sa.Column("switch_finished_at", sa.DateTime(), nullable=True),
        sa.Column("last_switch_duration_ms", sa.Integer(), nullable=True),
        sa.Column("last_failure_kind", sa.String(length=32), nullable=True),
        sa.Column("last_failure_reason", sa.Text(), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        "INSERT INTO gpu_scheduler_state (id, model_group, model_status) "
        "VALUES (1, 'none', 'unloaded')"
    )
    # §9 waiting_gpu 汇总按 status 过滤，补齐索引
    op.create_index("ix_kb_extract_jobs_status", "kb_extract_jobs", ["status"])
    op.create_index("ix_kb_post_jobs_status", "kb_post_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_kb_post_jobs_status", table_name="kb_post_jobs")
    op.drop_index("ix_kb_extract_jobs_status", table_name="kb_extract_jobs")
    op.drop_table("gpu_scheduler_state")
