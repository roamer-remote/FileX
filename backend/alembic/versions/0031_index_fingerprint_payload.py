"""061 P0-C: store fingerprint payload JSON for mismatch diff logging.

Revision ID: 0031_index_fingerprint_payload
Revises: 0030_index_fingerprint
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0031_index_fingerprint_payload"
down_revision: Union[str, None] = "0030_index_fingerprint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("files", sa.Column("index_fingerprint_payload", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("files", "index_fingerprint_payload")
