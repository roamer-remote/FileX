"""049 Phase A: kb_raptor_* system settings defaults.

Revision ID: 0023_kb_raptor_settings
Revises: 0022_files_md_content_hash
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0023_kb_raptor_settings"
down_revision: Union[str, None] = "0022_files_md_content_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (setting_key, value) VALUES
            ('kb_raptor_enabled', 'false'),
            ('kb_raptor_min_chars', '30000'),
            ('kb_raptor_max_levels', '3'),
            ('kb_raptor_max_summaries_per_file', '32'),
            ('kb_raptor_ollama_timeout_sec', '120'),
            ('kb_raptor_fail_open', 'true'),
            ('kb_raptor_drill_k', '5'),
            ('kb_raptor_drill_score_factor', '0.95')
        ON CONFLICT (setting_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM system_settings WHERE setting_key IN (
            'kb_raptor_enabled',
            'kb_raptor_min_chars',
            'kb_raptor_max_levels',
            'kb_raptor_max_summaries_per_file',
            'kb_raptor_ollama_timeout_sec',
            'kb_raptor_fail_open',
            'kb_raptor_drill_k',
            'kb_raptor_drill_score_factor'
        )
        """
    )
