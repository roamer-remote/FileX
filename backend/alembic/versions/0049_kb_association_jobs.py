"""144 durable association extraction jobs.

Revision ID: 0049_kb_association_jobs
Revises: 0048_kb_association_facts
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0049_kb_association_jobs"
down_revision: Union[str, None] = "0048_kb_association_facts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_association_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_association_jobs_user_id", "kb_association_jobs", ["user_id"])
    op.create_index("ix_kb_association_jobs_file_id", "kb_association_jobs", ["file_id"])
    op.create_index("ix_kb_association_jobs_status", "kb_association_jobs", ["status"])
    op.create_index("ix_kb_association_jobs_running_heartbeat", "kb_association_jobs", ["status", "heartbeat_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_kb_association_jobs_running_heartbeat", table_name="kb_association_jobs")
    op.drop_index("ix_kb_association_jobs_status", table_name="kb_association_jobs")
    op.drop_index("ix_kb_association_jobs_file_id", table_name="kb_association_jobs")
    op.drop_index("ix_kb_association_jobs_user_id", table_name="kb_association_jobs")
    op.drop_table("kb_association_jobs")
