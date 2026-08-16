"""wechat_auth: users 微信字段 + wechat_oauth_states 表

Revision ID: 0002_wechat_auth
Revises: 0001_squash_all
Create Date: 2026-05-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_wechat_auth"
down_revision: Union[str, None] = "0001_squash_all"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("wechat_openid", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("wechat_unionid", sa.String(length=64), nullable=True))
    op.create_index("ix_users_wechat_openid", "users", ["wechat_openid"], unique=True)

    op.create_table(
        "wechat_oauth_states",
        sa.Column("state", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=16), server_default="login", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("bind_user_id", sa.Integer(), nullable=True),
        sa.Column("success_user_id", sa.Integer(), nullable=True),
        sa.Column("pending_openid", sa.String(length=64), nullable=True),
        sa.Column("pending_unionid", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["bind_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["success_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index(
        "ix_wechat_oauth_states_bind_user_id",
        "wechat_oauth_states",
        ["bind_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_wechat_oauth_states_bind_user_id", table_name="wechat_oauth_states")
    op.drop_table("wechat_oauth_states")
    op.drop_index("ix_users_wechat_openid", table_name="users")
    op.drop_column("users", "wechat_unionid")
    op.drop_column("users", "wechat_openid")
