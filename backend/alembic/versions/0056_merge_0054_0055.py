"""Merge 0054 and 0055 heads into single migration chain.

Revision ID: 1dce6f92fd70
Revises: 0054_assoc_state_version, 0055_kb_multi_repr
Create Date: 2026-07-20 23:17:03.277342

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1dce6f92fd70'
down_revision: Union[str, Sequence[str], None] = ('0054_assoc_state_version', '0055_kb_multi_repr')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
