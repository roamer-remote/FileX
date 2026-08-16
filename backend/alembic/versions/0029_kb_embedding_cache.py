"""061 P0-A: kb_embedding_cache for embed vector reuse.

Revision ID: 0029_kb_embedding_cache
Revises: 0028_department_root_rename
"""

from typing import Sequence, Union

from alembic import op

from config import OLLAMA_EMBED_DIM

revision: str = "0029_kb_embedding_cache"
down_revision: Union[str, None] = "0028_department_root_rename"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dim = OLLAMA_EMBED_DIM
    op.execute(
        f"""
        CREATE TABLE kb_embedding_cache (
            id BIGSERIAL PRIMARY KEY,
            embed_input_hash VARCHAR(64) NOT NULL,
            embedding_model VARCHAR(64) NOT NULL,
            embedding vector({dim}) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (embed_input_hash, embedding_model)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_kb_embedding_cache_embed_input_hash
        ON kb_embedding_cache (embed_input_hash)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_embedding_cache_embed_input_hash")
    op.drop_table("kb_embedding_cache")
