"""wechat_nickname: 用户微信昵称与 OAuth 暂存

Revision ID: 0003_wechat_nickname
Revises: 0002_wechat_auth
Create Date: 2026-05-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_wechat_nickname"
down_revision: Union[str, None] = "0002_wechat_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("wechat_nickname", sa.String(length=128), nullable=True))
    op.add_column(
        "wechat_oauth_states",
        sa.Column("pending_nickname", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wechat_oauth_states", "pending_nickname")
    op.drop_column("users", "wechat_nickname")
