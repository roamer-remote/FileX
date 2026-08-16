"""060：内置根部门「组织」重命名为「企业组织」。

Revision ID: 0028_department_root_rename
Revises: 0027_enterprise_rbac_cutover
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0028_department_root_rename"
down_revision: Union[str, None] = "0027_enterprise_rbac_cutover"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE departments
        SET name = '企业组织'
        WHERE parent_id IS NULL AND name = '组织'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE departments
        SET name = '组织'
        WHERE parent_id IS NULL AND name = '企业组织'
        """
    )
