"""077 P0: kb_events + kb_event_entities for SAG event–entity indexing.

Revision ID: 0035_kb_sag_events
Revises: 0034_extracted_at_beijing
"""

from typing import Sequence, Union

from alembic import op

from config import OLLAMA_EMBED_DIM

revision: str = "0035_kb_sag_events"
down_revision: Union[str, None] = "0034_extracted_at_beijing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dim = OLLAMA_EMBED_DIM
    op.execute(
        f"""
        CREATE TABLE kb_events (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            chunk_id BIGINT NOT NULL UNIQUE REFERENCES kb_chunks(id) ON DELETE CASCADE,
            title VARCHAR(512) NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            title_embedding vector({dim}),
            extract_layer VARCHAR(16) NOT NULL,
            created_at TIMESTAMP DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_kb_events_user_id ON kb_events (user_id)")
    op.execute("CREATE INDEX ix_kb_events_workspace_id ON kb_events (workspace_id)")
    op.execute("CREATE INDEX ix_kb_events_file_id ON kb_events (file_id)")
    op.execute("CREATE UNIQUE INDEX ix_kb_events_chunk_id ON kb_events (chunk_id)")
    op.execute(
        "CREATE INDEX ix_kb_events_user_workspace_file ON kb_events (user_id, workspace_id, file_id)"
    )

    op.execute(
        f"""
        CREATE TABLE kb_event_entities (
            id BIGSERIAL PRIMARY KEY,
            event_id BIGINT NOT NULL REFERENCES kb_events(id) ON DELETE CASCADE,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
            entity_name VARCHAR(256) NOT NULL,
            entity_type VARCHAR(32) NOT NULL DEFAULT 'concept',
            entity_embedding vector({dim}),
            created_at TIMESTAMP DEFAULT now(),
            UNIQUE (event_id, entity_name)
        )
        """
    )
    op.execute("CREATE INDEX ix_kb_event_entities_event_id ON kb_event_entities (event_id)")
    op.execute("CREATE INDEX ix_kb_event_entities_file_id ON kb_event_entities (file_id)")
    op.execute("CREATE INDEX ix_kb_event_entities_workspace_id ON kb_event_entities (workspace_id)")
    op.execute(
        "CREATE INDEX ix_kb_event_entities_file_entity ON kb_event_entities (file_id, entity_name)"
    )
    op.execute(
        "CREATE INDEX ix_kb_event_entities_workspace_entity ON kb_event_entities (workspace_id, entity_name)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_event_entities_workspace_entity")
    op.execute("DROP INDEX IF EXISTS ix_kb_event_entities_file_entity")
    op.execute("DROP INDEX IF EXISTS ix_kb_event_entities_workspace_id")
    op.execute("DROP INDEX IF EXISTS ix_kb_event_entities_file_id")
    op.execute("DROP INDEX IF EXISTS ix_kb_event_entities_event_id")
    op.execute("DROP TABLE IF EXISTS kb_event_entities")
    op.execute("DROP INDEX IF EXISTS ix_kb_events_user_workspace_file")
    op.execute("DROP INDEX IF EXISTS ix_kb_events_chunk_id")
    op.execute("DROP INDEX IF EXISTS ix_kb_events_file_id")
    op.execute("DROP INDEX IF EXISTS ix_kb_events_workspace_id")
    op.execute("DROP INDEX IF EXISTS ix_kb_events_user_id")
    op.execute("DROP TABLE IF EXISTS kb_events")
