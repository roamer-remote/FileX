"""107 P3: agent_run_retention_days system setting.

Revision ID: 0040_agent_run_retention_days
Revises: 0039_agent_runs
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0040_agent_run_retention_days"
down_revision: Union[str, None] = "0039_agent_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (setting_key, value)
        VALUES ('agent_run_retention_days', '30')
        ON CONFLICT (setting_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE setting_key = 'agent_run_retention_days'"
    )
