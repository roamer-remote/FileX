"""030: kb_chunks content_kind + content_meta for multimodal RAG.

Revision ID: 0015_kb_chunk_content_kind
Revises: 0014_kb_search_default_top_k
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0015_kb_chunk_content_kind"
down_revision: Union[str, None] = "0014_kb_search_default_top_k"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kb_chunks", sa.Column("content_kind", sa.String(length=16), nullable=True))
    op.add_column("kb_chunks", sa.Column("content_meta", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("kb_chunks", "content_meta")
    op.drop_column("kb_chunks", "content_kind")
