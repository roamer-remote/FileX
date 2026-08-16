"""064: OKF metadata columns on files.

Revision ID: 0033_files_okf_metadata
Revises: 0032_kb_chunk_vectors
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0033_files_okf_metadata"
down_revision: Union[str, None] = "0032_kb_chunk_vectors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE files ADD COLUMN IF NOT EXISTS okf_concept_path VARCHAR(512);
        ALTER TABLE files ADD COLUMN IF NOT EXISTS okf_type VARCHAR(128);
        ALTER TABLE files ADD COLUMN IF NOT EXISTS okf_metadata JSONB;
        ALTER TABLE files ADD COLUMN IF NOT EXISTS okf_reserved_role VARCHAR(16);
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_files_okf_path_shared
        ON files (workspace_id, okf_concept_path)
        WHERE workspace_id IS NOT NULL AND okf_concept_path IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_files_okf_path_personal
        ON files (user_id, okf_concept_path)
        WHERE workspace_id IS NULL AND okf_concept_path IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_files_okf_path_personal")
    op.execute("DROP INDEX IF EXISTS uq_files_okf_path_shared")
    op.execute(
        """
        ALTER TABLE files DROP COLUMN IF EXISTS okf_reserved_role;
        ALTER TABLE files DROP COLUMN IF EXISTS okf_metadata;
        ALTER TABLE files DROP COLUMN IF EXISTS okf_type;
        ALTER TABLE files DROP COLUMN IF EXISTS okf_concept_path;
        """
    )
