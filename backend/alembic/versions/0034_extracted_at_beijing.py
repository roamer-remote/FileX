"""Fix files.extracted_at: historical UTC naive -> Beijing wall clock (+8h).

Revision ID: 0034_extracted_at_beijing
Revises: 0033_files_okf_metadata
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0034_extracted_at_beijing"
down_revision: Union[str, None] = "0033_files_okf_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE files
        SET extracted_at = extracted_at + INTERVAL '8 hours'
        WHERE extracted_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE files
        SET extracted_at = extracted_at - INTERVAL '8 hours'
        WHERE extracted_at IS NOT NULL
        """
    )
