"""059 企业 RBAC：部门/角色 seed 与辅助查询。

Revision ID: 0025_enterprise_rbac
Revises: 0024_kb_external_sync
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0025_enterprise_rbac"
down_revision: Union[str, None] = "0024_kb_external_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BUILTIN_ROLES = (
    ("space_admin", "空间管理员", "空间级 ACL 主体标签"),
    ("folder_admin", "目录管理员", "按目录授 manage"),
    ("editor", "编辑者", "按目录授 write"),
    ("viewer", "只读者", "按目录授 read"),
    ("auditor", "审计员", "按目录授 read；检索审计只读"),
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE departments (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            parent_id INTEGER REFERENCES departments(id) ON DELETE RESTRICT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_departments_parent_id ON departments (parent_id)")

    op.execute(
        """
        CREATE TABLE groups (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            description VARCHAR(500),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE enterprise_roles (
            id SERIAL PRIMARY KEY,
            slug VARCHAR(64) NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL,
            description VARCHAR(500),
            is_builtin BOOLEAN NOT NULL DEFAULT false,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_enterprise_roles_slug ON enterprise_roles (slug)")

    op.execute(
        """
        CREATE TABLE workspace_user_roles (
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role_id INTEGER NOT NULL REFERENCES enterprise_roles(id) ON DELETE CASCADE,
            PRIMARY KEY (workspace_id, user_id, role_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE user_groups (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, group_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_user_groups_group_id ON user_groups (group_id)")

    op.execute(
        """
        CREATE TABLE folder_acl (
            id SERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
            subject_type VARCHAR(16) NOT NULL,
            subject_id INTEGER NOT NULL,
            permission VARCHAR(16) NOT NULL,
            created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_folder_acl_target UNIQUE NULLS NOT DISTINCT (
                workspace_id, folder_id, subject_type, subject_id
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_folder_acl_workspace_folder ON folder_acl (workspace_id, folder_id)")
    op.execute("CREATE INDEX ix_folder_acl_subject ON folder_acl (subject_type, subject_id)")

    op.execute("ALTER TABLE users ADD COLUMN primary_department_id INTEGER")

    op.execute(
        """
        WITH root AS (
            INSERT INTO departments (name, parent_id, sort_order)
            VALUES ('组织', NULL, 0)
            RETURNING id
        ),
        unassigned AS (
            INSERT INTO departments (name, parent_id, sort_order)
            SELECT '未分配', root.id, 0 FROM root
            RETURNING id
        )
        UPDATE users
        SET primary_department_id = (SELECT id FROM unassigned)
        WHERE primary_department_id IS NULL
        """
    )

    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN primary_department_id SET NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD CONSTRAINT fk_users_primary_department
        FOREIGN KEY (primary_department_id) REFERENCES departments(id) ON DELETE RESTRICT
        """
    )
    op.execute("CREATE INDEX ix_users_primary_department_id ON users (primary_department_id)")

    for slug, name, description in _BUILTIN_ROLES:
        op.execute(
            f"""
            INSERT INTO enterprise_roles (slug, name, description, is_builtin, is_active)
            VALUES ('{slug}', '{name}', '{description}', true, true)
            """
        )

    op.execute(
        """
        INSERT INTO system_settings (setting_key, value) VALUES
            ('enterprise_rbac_enabled', 'false'),
            ('enterprise_rbac_write_mode', 'dual')
        ON CONFLICT (setting_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE setting_key IN ('enterprise_rbac_enabled', 'enterprise_rbac_write_mode')")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_primary_department")
    op.execute("DROP INDEX IF EXISTS ix_users_primary_department_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS primary_department_id")
    op.execute("DROP TABLE IF EXISTS folder_acl")
    op.execute("DROP TABLE IF EXISTS user_groups")
    op.execute("DROP TABLE IF EXISTS workspace_user_roles")
    op.execute("DROP TABLE IF EXISTS enterprise_roles")
    op.execute("DROP TABLE IF EXISTS groups")
    op.execute("DROP TABLE IF EXISTS departments")
