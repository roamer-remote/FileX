"""039: user_ui_state per-user UI preferences JSON document.

Revision ID: 0018_user_ui_state
Revises: 0017_user_settings
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0018_user_ui_state"
down_revision: Union[str, None] = "0017_user_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_ui_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_ui_state_user_id"),
    )
    op.create_index("ix_user_ui_state_user_id", "user_ui_state", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_ui_state_user_id", table_name="user_ui_state")
    op.drop_table("user_ui_state")
