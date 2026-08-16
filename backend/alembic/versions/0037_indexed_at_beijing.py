"""Fix files.indexed_at: historical UTC naive -> Beijing wall clock (+8h).

Revision ID: 0037_indexed_at_beijing
Revises: 0036_mineru_32g_recommended
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0037_indexed_at_beijing"
down_revision: Union[str, None] = "0036_mineru_32g_recommended"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE files
        SET indexed_at = indexed_at + INTERVAL '8 hours'
        WHERE indexed_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE files
        SET indexed_at = indexed_at - INTERVAL '8 hours'
        WHERE indexed_at IS NOT NULL
        """
    )
