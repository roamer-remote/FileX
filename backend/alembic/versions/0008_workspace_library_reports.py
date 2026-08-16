"""016: workspace_library_reports + file_wiki_links.content_hash

Revision ID: 0008_workspace_library_reports
Revises: 0007_wiki_compile_queue
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_workspace_library_reports"
down_revision: Union[str, None] = "0007_wiki_compile_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_library_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("triggered_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_library_reports_workspace_id", "workspace_library_reports", ["workspace_id"])
    op.create_index(
        "uq_workspace_library_report_ready",
        "workspace_library_reports",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ready'"),
    )
    op.add_column("file_wiki_links", sa.Column("content_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("file_wiki_links", "content_hash")
    op.drop_index("uq_workspace_library_report_ready", table_name="workspace_library_reports")
    op.drop_index("ix_workspace_library_reports_workspace_id", table_name="workspace_library_reports")
    op.drop_table("workspace_library_reports")
