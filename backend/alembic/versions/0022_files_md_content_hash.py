"""048: files.md_content_hash for incremental extract skip.

Revision ID: 0022_files_md_content_hash
Revises: 0021_kb_index_manual_override
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022_files_md_content_hash"
down_revision: Union[str, None] = "0021_kb_index_manual_override"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column("md_content_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("files", "md_content_hash")
