"""114 KB post async: kb_post_jobs + files.kb_post_*.

Revision ID: 0041_kb_post_jobs
Revises: 0040_agent_run_retention_days
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0041_kb_post_jobs"
down_revision: Union[str, None] = "0040_agent_run_retention_days"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_post_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("index_job_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("force", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("pipeline_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("post_entity_ms", sa.Integer(), nullable=True),
        sa.Column("post_sag_ms", sa.Integer(), nullable=True),
        sa.Column("post_raptor_ms", sa.Integer(), nullable=True),
        sa.Column("post_skip_reason", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["index_job_id"], ["kb_index_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_post_jobs_user_id", "kb_post_jobs", ["user_id"])
    op.create_index("ix_kb_post_jobs_file_id", "kb_post_jobs", ["file_id"])
    op.create_index("ix_kb_post_jobs_index_job_id", "kb_post_jobs", ["index_job_id"])

    op.add_column(
        "files",
        sa.Column("kb_post_status", sa.String(length=16), server_default="pending", nullable=False),
    )
    op.add_column("files", sa.Column("kb_post_error", sa.Text(), nullable=True))
    op.add_column("files", sa.Column("kb_post_at", sa.DateTime(), nullable=True))

    # M4: 存量 ready 视为 post 已完成；不重跑 post
    op.execute("UPDATE files SET kb_post_status = 'ready' WHERE index_status = 'ready'")

    op.execute(
        """
        INSERT INTO system_settings (setting_key, value)
        VALUES ('kb_post_async_enabled', 'true')
        ON CONFLICT (setting_key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO system_settings (setting_key, value)
        VALUES ('kb_post_max_attempts', '3')
        ON CONFLICT (setting_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_column("files", "kb_post_at")
    op.drop_column("files", "kb_post_error")
    op.drop_column("files", "kb_post_status")
    op.drop_index("ix_kb_post_jobs_index_job_id", table_name="kb_post_jobs")
    op.drop_index("ix_kb_post_jobs_file_id", table_name="kb_post_jobs")
    op.drop_index("ix_kb_post_jobs_user_id", table_name="kb_post_jobs")
    op.drop_table("kb_post_jobs")
    op.execute("DELETE FROM system_settings WHERE setting_key IN ('kb_post_async_enabled', 'kb_post_max_attempts')")
