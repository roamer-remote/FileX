"""061 P0-C: files.index_pipeline_fingerprint + raptor skip metadata.

Revision ID: 0030_index_fingerprint
Revises: 0029_kb_embedding_cache
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0030_index_fingerprint"
down_revision: Union[str, None] = "0029_kb_embedding_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("files", sa.Column("index_pipeline_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("files", sa.Column("raptor_built_chunk_count", sa.Integer(), nullable=True))
    op.add_column("files", sa.Column("raptor_built_md_chars", sa.Integer(), nullable=True))
    # 历史指纹回填见 scripts/kb_backfill_fingerprint.py（须在 0031 payload 列就绪后执行）


def downgrade() -> None:
    op.drop_column("files", "raptor_built_md_chars")
    op.drop_column("files", "raptor_built_chunk_count")
    op.drop_column("files", "index_pipeline_fingerprint")
