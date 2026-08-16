"""010: wiki_compile_queue

Revision ID: 0007_wiki_compile_queue
Revises: 0006_wiki_interlink
Create Date: 2026-06-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_wiki_compile_queue"
down_revision: Union[str, None] = "0006_wiki_interlink"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wiki_compile_queue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("wiki_slug", sa.String(128), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wiki_compile_queue_user_id", "wiki_compile_queue", ["user_id"])
    op.create_index("ix_wiki_compile_queue_workspace_id", "wiki_compile_queue", ["workspace_id"])
    op.create_index(
        "ix_wiki_compile_queue_pending_slug",
        "wiki_compile_queue",
        ["user_id", "workspace_id", "wiki_slug"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_wiki_compile_queue_pending_slug", table_name="wiki_compile_queue")
    op.drop_index("ix_wiki_compile_queue_workspace_id", table_name="wiki_compile_queue")
    op.drop_index("ix_wiki_compile_queue_user_id", table_name="wiki_compile_queue")
    op.drop_table("wiki_compile_queue")
