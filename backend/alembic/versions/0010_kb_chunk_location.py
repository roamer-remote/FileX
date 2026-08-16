"""025: kb_chunks location columns for RAG citation labels.

Revision ID: 0010_kb_chunk_location
Revises: 0009_wechat_poll_secret
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_kb_chunk_location"
down_revision: Union[str, None] = "0009_wechat_poll_secret"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kb_chunks", sa.Column("loc_type", sa.String(length=16), nullable=True))
    op.add_column("kb_chunks", sa.Column("loc_start", sa.Integer(), nullable=True))
    op.add_column("kb_chunks", sa.Column("loc_end", sa.Integer(), nullable=True))
    op.add_column("kb_chunks", sa.Column("loc_label", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("kb_chunks", "loc_label")
    op.drop_column("kb_chunks", "loc_end")
    op.drop_column("kb_chunks", "loc_start")
    op.drop_column("kb_chunks", "loc_type")
