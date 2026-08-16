"""047: files.kb_index_manual_override + kb_index_jobs.force.

Revision ID: 0021_kb_index_manual_override
Revises: 0020_insavlo_extract_state
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_kb_index_manual_override"
down_revision: Union[str, None] = "0020_insavlo_extract_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column(
            "kb_index_manual_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "kb_index_jobs",
        sa.Column(
            "force",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("kb_index_jobs", "force")
    op.drop_column("files", "kb_index_manual_override")
