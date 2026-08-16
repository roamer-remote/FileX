"""062: split kb chunk vectors into kb_chunk_vectors.

Revision ID: 0032_kb_chunk_vectors
Revises: 0031_index_fingerprint_payload
"""

from typing import Sequence, Union

from alembic import op

from config import OLLAMA_EMBED_DIM

revision: str = "0032_kb_chunk_vectors"
down_revision: Union[str, None] = "0031_index_fingerprint_payload"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dim = OLLAMA_EMBED_DIM
    op.execute(
        f"""
        CREATE TABLE kb_chunk_vectors (
            chunk_id BIGINT PRIMARY KEY REFERENCES kb_chunks(id) ON DELETE CASCADE,
            file_id INTEGER NOT NULL,
            workspace_id INTEGER,
            user_id INTEGER NOT NULL,
            content_kind VARCHAR(16),
            embedding vector({dim}) NOT NULL,
            embedding_model VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_kb_chunk_vectors_file_id ON kb_chunk_vectors (file_id)")
    op.execute("CREATE INDEX ix_kb_chunk_vectors_workspace_id ON kb_chunk_vectors (workspace_id)")
    op.execute("CREATE INDEX ix_kb_chunk_vectors_user_id ON kb_chunk_vectors (user_id)")
    op.execute(
        f"""
        CREATE INDEX ix_kb_chunk_vectors_embedding_hnsw
        ON kb_chunk_vectors USING hnsw (embedding vector_cosine_ops)
        """
    )
    op.execute(
        """
        INSERT INTO kb_chunk_vectors (
            chunk_id, file_id, workspace_id, user_id, content_kind,
            embedding, embedding_model, created_at
        )
        SELECT
            id, file_id, workspace_id, user_id, content_kind,
            embedding, embedding_model, COALESCE(created_at, now())
        FROM kb_chunks
        WHERE embedding IS NOT NULL
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_embedding_hnsw")
    op.execute("ALTER TABLE kb_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE kb_chunks DROP COLUMN IF EXISTS embedding_model")


def downgrade() -> None:
    dim = OLLAMA_EMBED_DIM
    op.execute(f"ALTER TABLE kb_chunks ADD COLUMN embedding vector({dim})")
    op.execute("ALTER TABLE kb_chunks ADD COLUMN embedding_model VARCHAR(64)")
    op.execute(
        """
        UPDATE kb_chunks c
        SET embedding = v.embedding,
            embedding_model = v.embedding_model
        FROM kb_chunk_vectors v
        WHERE v.chunk_id = c.id
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_kb_chunks_embedding_hnsw
        ON kb_chunks USING hnsw (embedding vector_cosine_ops)
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_kb_chunk_vectors_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_kb_chunk_vectors_workspace_id")
    op.execute("DROP INDEX IF EXISTS ix_kb_chunk_vectors_user_id")
    op.execute("DROP INDEX IF EXISTS ix_kb_chunk_vectors_file_id")
    op.execute("DROP TABLE IF EXISTS kb_chunk_vectors")
