"""persist raw upload byte SHA-256 for 187-P2 source provenance.

Revision ID: 0068_files_source_sha256
Revises: 0067_kb_overlay_reindex_state
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0068_files_source_sha256"
down_revision: str | None = "0067_kb_overlay_reindex_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("files", sa.Column("source_sha256", sa.String(length=64), nullable=True))
    op.create_index("ix_files_source_sha256", "files", ["source_sha256"])


def downgrade() -> None:
    op.drop_index("ix_files_source_sha256", table_name="files")
    op.drop_column("files", "source_sha256")
