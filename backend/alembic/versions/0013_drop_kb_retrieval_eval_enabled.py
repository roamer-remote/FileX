"""029: drop kb_retrieval_eval_enabled system setting.

Revision ID: 0013_drop_kb_retrieval_eval
Revises: 0012_kb_search_cache
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0013_drop_kb_retrieval_eval"
down_revision: Union[str, None] = "0012_kb_search_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE setting_key = 'kb_retrieval_eval_enabled'"
    )


def downgrade() -> None:
    # 不恢复删除前的原始 value（可能为 false）；回滚仅插入默认 true，满足 schema 默认。
    op.execute(
        """
        INSERT INTO system_settings (setting_key, value)
        VALUES ('kb_retrieval_eval_enabled', 'true')
        ON CONFLICT (setting_key) DO NOTHING
        """
    )
