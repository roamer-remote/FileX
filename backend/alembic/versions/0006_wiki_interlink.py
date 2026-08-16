"""009: Wiki interlink tables and file wiki fields

Revision ID: 0006_wiki_interlink
Revises: 0005_zhparser_fts
Create Date: 2026-06-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_wiki_interlink"
down_revision: Union[str, None] = "0005_zhparser_fts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

page_kind_enum = sa.Enum(
    "source",
    "entity",
    "concept",
    "synthesis",
    name="page_kind_enum",
)


def upgrade() -> None:
    bind = op.get_bind()
    page_kind_enum.create(bind, checkfirst=True)

    op.add_column(
        "files",
        sa.Column(
            "page_kind",
            page_kind_enum,
            nullable=False,
            server_default="source",
        ),
    )
    op.add_column("files", sa.Column("wiki_slug", sa.String(128), nullable=True))
    op.add_column(
        "files",
        sa.Column("wiki_outlink_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_files_user_workspace_wiki_slug",
        "files",
        ["user_id", "workspace_id", "wiki_slug"],
        unique=True,
        postgresql_where=sa.text("wiki_slug IS NOT NULL"),
    )

    op.create_table(
        "file_wiki_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_file_id", sa.Integer(), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_file_id", sa.Integer(), sa.ForeignKey("files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_wiki_slug", sa.String(128), nullable=True),
        sa.Column("target_file_id_raw", sa.Integer(), nullable=True),
        sa.Column("link_kind", sa.String(16), nullable=False),
        sa.Column("link_text", sa.String(256), nullable=True),
        sa.Column("occurrence_index", sa.Integer(), nullable=False),
        sa.Column("anchor_id", sa.String(128), nullable=False, unique=True),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("broken_reason", sa.String(16), nullable=True),
        sa.UniqueConstraint("source_file_id", "occurrence_index", name="uq_file_wiki_links_source_occ"),
    )
    op.create_index("ix_file_wiki_links_source", "file_wiki_links", ["source_file_id"])
    op.create_index("ix_file_wiki_links_target", "file_wiki_links", ["target_file_id"])

    op.create_table(
        "kb_log_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entry", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_kb_log_entries_user", "kb_log_entries", ["user_id"])
    op.create_index("ix_kb_log_entries_workspace", "kb_log_entries", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_kb_log_entries_workspace", table_name="kb_log_entries")
    op.drop_index("ix_kb_log_entries_user", table_name="kb_log_entries")
    op.drop_table("kb_log_entries")
    op.drop_index("ix_file_wiki_links_target", table_name="file_wiki_links")
    op.drop_index("ix_file_wiki_links_source", table_name="file_wiki_links")
    op.drop_table("file_wiki_links")
    op.drop_index("ix_files_user_workspace_wiki_slug", table_name="files")
    op.drop_column("files", "wiki_outlink_count")
    op.drop_column("files", "wiki_slug")
    op.drop_column("files", "page_kind")
    page_kind_enum.drop(op.get_bind(), checkfirst=True)
