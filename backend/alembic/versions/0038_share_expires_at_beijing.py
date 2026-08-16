"""Fix share_links.expires_at: historical UTC naive -> Beijing wall clock (+8h).

Revision ID: 0038_share_expires_at_beijing
Revises: 0037_indexed_at_beijing
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0038_share_expires_at_beijing"
down_revision: Union[str, None] = "0037_indexed_at_beijing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE share_links
        SET expires_at = expires_at + INTERVAL '8 hours'
        WHERE expires_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE share_links
        SET expires_at = expires_at - INTERVAL '8 hours'
        WHERE expires_at IS NOT NULL
        """
    )
