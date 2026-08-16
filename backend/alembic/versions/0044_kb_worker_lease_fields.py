"""127: KB worker lease and heartbeat fields.

Revision ID: 0044_kb_worker_lease_fields
Revises: 0043_kb_post_job_raptor_flags
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0044_kb_worker_lease_fields"
down_revision: Union[str, None] = "0043_kb_post_job_raptor_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_job_lease_columns(table_name: str) -> None:
    op.add_column(table_name, sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    op.add_column(table_name, sa.Column("worker_id", sa.String(length=128), nullable=True))
    op.add_column(table_name, sa.Column("claimed_at", sa.DateTime(), nullable=True))
    op.add_column(
        table_name,
        sa.Column("lease_generation", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index(f"ix_{table_name}_worker_id", table_name, ["worker_id"])
    op.create_index(f"ix_{table_name}_heartbeat_at", table_name, ["heartbeat_at"])


def _drop_job_lease_columns(table_name: str) -> None:
    op.drop_index(f"ix_{table_name}_heartbeat_at", table_name=table_name)
    op.drop_index(f"ix_{table_name}_worker_id", table_name=table_name)
    op.drop_column(table_name, "lease_generation")
    op.drop_column(table_name, "claimed_at")
    op.drop_column(table_name, "worker_id")
    op.drop_column(table_name, "heartbeat_at")


def upgrade() -> None:
    _add_job_lease_columns("kb_index_jobs")
    _add_job_lease_columns("kb_post_jobs")


def downgrade() -> None:
    _drop_job_lease_columns("kb_post_jobs")
    _drop_job_lease_columns("kb_index_jobs")
