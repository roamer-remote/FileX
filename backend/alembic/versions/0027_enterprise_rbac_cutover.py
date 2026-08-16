"""059 S4：enterprise_rbac_cutover 系统参数。

Revision ID: 0027_enterprise_rbac_cutover
Revises: 0026_enterprise_rbac_tidy
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0027_enterprise_rbac_cutover"
down_revision: Union[str, None] = "0026_enterprise_rbac_tidy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (setting_key, value)
        VALUES ('enterprise_rbac_cutover', 'false')
        ON CONFLICT (setting_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE setting_key = 'enterprise_rbac_cutover'")
