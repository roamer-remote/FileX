"""059 P0 评审修复：移除冗余 UNIQUE、补 user_groups.group_id 索引。

Revision ID: 0026_enterprise_rbac_tidy
Revises: 0025_enterprise_rbac
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0026_enterprise_rbac_tidy"
down_revision: Union[str, None] = "0025_enterprise_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workspace_user_roles DROP CONSTRAINT IF EXISTS uq_workspace_user_roles_ws_user_role"
    )
    op.execute("ALTER TABLE user_groups DROP CONSTRAINT IF EXISTS uq_user_groups_user_group")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_groups_group_id ON user_groups (group_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_groups_group_id")
    op.execute(
        """
        ALTER TABLE user_groups
        ADD CONSTRAINT uq_user_groups_user_group UNIQUE (user_id, group_id)
        """
    )
    op.execute(
        """
        ALTER TABLE workspace_user_roles
        ADD CONSTRAINT uq_workspace_user_roles_ws_user_role
        UNIQUE (workspace_id, user_id, role_id)
        """
    )
