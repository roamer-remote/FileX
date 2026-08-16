"""118: kb_post_jobs raptor_only + force_raptor_settings.

Revision ID: 0043_kb_post_job_raptor_flags
Revises: 0042_mineru_settings_seed
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0043_kb_post_job_raptor_flags"
down_revision: Union[str, None] = "0042_mineru_settings_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kb_post_jobs",
        sa.Column("raptor_only", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "kb_post_jobs",
        sa.Column("force_raptor_settings", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("kb_post_jobs", "force_raptor_settings")
    op.drop_column("kb_post_jobs", "raptor_only")
