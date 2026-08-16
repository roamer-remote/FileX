"""049 Phase B: kb_external_sync_sources + kb_external_sync_items.

Revision ID: 0024_kb_external_sync
Revises: 0023_kb_raptor_settings
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0024_kb_external_sync"
down_revision: Union[str, None] = "0023_kb_raptor_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE kb_external_sync_sources (
            id SERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider VARCHAR(32) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            delete_policy VARCHAR(32) NOT NULL DEFAULT 'keep_file',
            config_public_json JSONB NOT NULL DEFAULT '{}',
            secret_ciphertext BYTEA,
            last_sync_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_kb_external_sync_sources_workspace
        ON kb_external_sync_sources (workspace_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_kb_external_sync_sources_user
        ON kb_external_sync_sources (user_id)
        """
    )
    op.execute(
        """
        CREATE TABLE kb_external_sync_items (
            id SERIAL PRIMARY KEY,
            source_id INTEGER NOT NULL
                REFERENCES kb_external_sync_sources(id) ON DELETE CASCADE,
            external_key VARCHAR(512) NOT NULL,
            external_uri TEXT,
            external_updated_at TIMESTAMPTZ,
            file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
            content_hash VARCHAR(64),
            sync_status VARCHAR(32) NOT NULL DEFAULT 'active',
            deleted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_external_sync_items UNIQUE (source_id, external_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_kb_external_sync_items_source
        ON kb_external_sync_items (source_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_kb_external_sync_items_file
        ON kb_external_sync_items (file_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_external_sync_items_file")
    op.execute("DROP INDEX IF EXISTS ix_kb_external_sync_items_source")
    op.drop_table("kb_external_sync_items")
    op.execute("DROP INDEX IF EXISTS ix_kb_external_sync_sources_user")
    op.execute("DROP INDEX IF EXISTS ix_kb_external_sync_sources_workspace")
    op.drop_table("kb_external_sync_sources")
