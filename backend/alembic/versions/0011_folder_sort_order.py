"""027: folders.sort_order for sibling ordering.

Revision ID: 0011_folder_sort_order
Revises: 0010_kb_chunk_location
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_folder_sort_order"
down_revision: Union[str, None] = "0010_kb_chunk_location"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "folders",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY workspace_id, parent_id
                    ORDER BY created_at ASC, id ASC
                ) - 1 AS rn
            FROM folders
        )
        UPDATE folders AS f
        SET sort_order = ranked.rn
        FROM ranked
        WHERE f.id = ranked.id
        """
    )


def downgrade() -> None:
    op.drop_column("folders", "sort_order")
