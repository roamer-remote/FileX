"""036: user_settings sparse overrides for per-user KB preferences.

Revision ID: 0017_user_settings
Revises: 0016_kb_doc_entity_edges
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_user_settings"
down_revision: Union[str, None] = "0016_kb_doc_entity_edges"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("setting_key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "setting_key", name="uq_user_settings_user_key"),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_table("user_settings")
