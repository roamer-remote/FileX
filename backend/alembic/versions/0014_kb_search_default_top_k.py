"""030: kb_search_default_top_k system setting for smart search UI.

Revision ID: 0014_kb_search_default_top_k
Revises: 0013_drop_kb_retrieval_eval
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0014_kb_search_default_top_k"
down_revision: Union[str, None] = "0013_drop_kb_retrieval_eval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (setting_key, value)
        VALUES ('kb_search_default_top_k', '8')
        ON CONFLICT (setting_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE setting_key = 'kb_search_default_top_k'"
    )
