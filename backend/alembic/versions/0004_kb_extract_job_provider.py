"""kb_extract_jobs.provider: per-job extract engine override

Revision ID: 0004_kb_extract_job_provider
Revises: 0003_wechat_nickname
Create Date: 2026-05-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_kb_extract_job_provider"
down_revision: Union[str, None] = "0003_wechat_nickname"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kb_extract_jobs",
        sa.Column("provider", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("kb_extract_jobs", "provider")
