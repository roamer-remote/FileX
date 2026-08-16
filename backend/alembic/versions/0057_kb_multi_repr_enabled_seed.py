"""Seed kb_multi_repr_enabled system_setting (154: unlock RAPTOR multi-repr search path).

Revision ID: 0057_kb_multi_repr_enabled_seed
Revises: 1dce6f92fd70
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0057_kb_multi_repr_enabled_seed"
down_revision: Union[str, None] = "1dce6f92fd70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (setting_key, value)
        VALUES ('kb_multi_repr_enabled', 'true')
        ON CONFLICT (setting_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE setting_key = 'kb_multi_repr_enabled'"
    )
