"""023 P0: wechat_oauth_states.poll_secret 客户端绑定

Revision ID: 0009_wechat_poll_secret
Revises: 0008_workspace_library_reports
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_wechat_poll_secret"
down_revision: Union[str, None] = "0008_workspace_library_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wechat_oauth_states",
        sa.Column("poll_secret", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wechat_oauth_states", "poll_secret")
