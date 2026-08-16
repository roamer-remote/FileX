"""040: kb_extract_jobs.bypass_mineru_cache for force reextract.

Revision ID: 0019_extract_bypass_cache
Revises: 0018_user_ui_state
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_extract_bypass_cache"
down_revision: Union[str, None] = "0018_user_ui_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kb_extract_jobs",
        sa.Column(
            "bypass_mineru_cache",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("kb_extract_jobs", "bypass_mineru_cache")
