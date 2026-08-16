"""Add oom_retry_count to kb extract/post jobs (164 T-7)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0060_gpu_oom_retry_count"
down_revision: Union[str, None] = "0059_gpu_scheduler_lease_batch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kb_extract_jobs",
        sa.Column("oom_retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "kb_post_jobs",
        sa.Column("oom_retry_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("kb_post_jobs", "oom_retry_count")
    op.drop_column("kb_extract_jobs", "oom_retry_count")
