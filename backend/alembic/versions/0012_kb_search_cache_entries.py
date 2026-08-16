"""028: kb_search_cache_entries for query result cache.

Revision ID: 0012_kb_search_cache
Revises: 0011_folder_sort_order
"""

from typing import Sequence, Union

from alembic import op

from config import OLLAMA_EMBED_DIM

revision: str = "0012_kb_search_cache"
down_revision: Union[str, None] = "0011_folder_sort_order"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dim = OLLAMA_EMBED_DIM
    op.execute(
        f"""
        CREATE TABLE kb_search_cache_entries (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            scope_hash VARCHAR(64) NOT NULL,
            query_text TEXT NOT NULL,
            query_embedding vector({dim}) NOT NULL,
            response_payload JSONB NOT NULL,
            hit_count INTEGER NOT NULL DEFAULT 0,
            last_hit_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_kb_search_cache_user_ws_scope
        ON kb_search_cache_entries (user_id, workspace_id, scope_hash)
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_kb_search_cache_embedding_hnsw
        ON kb_search_cache_entries
        USING hnsw (query_embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_search_cache_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_kb_search_cache_user_ws_scope")
    op.drop_table("kb_search_cache_entries")
