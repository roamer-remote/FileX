"""Seed mineru_* system_settings rows from 32G recommended defaults.

Revision ID: 0042_mineru_settings_seed
Revises: 0041_kb_post_jobs
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0042_mineru_settings_seed"
down_revision: Union[str, None] = "0041_kb_post_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MINERU_DEFAULTS: tuple[tuple[str, str], ...] = (
    ("mineru_min_batch_mode", "auto"),
    ("mineru_min_batch_inference_size", "112"),
    ("mineru_min_batch_floor", "16"),
    ("mineru_parse_method", "auto"),
    ("mineru_formula_enable", "true"),
    ("mineru_table_enable", "true"),
    ("mineru_parse_timeout_sec", "1200"),
    ("mineru_rpc_timeout_sec", "3600"),
    ("mineru_page_chunk_enabled", "true"),
    ("mineru_page_chunk_threshold", "160"),
    ("mineru_page_chunk_pages", "64"),
    ("mineru_table_auto_rotate", "false"),
    ("mineru_table_rotate_max_tables", "8"),
    ("mineru_table_rotate_timeout_sec", "30"),
)


def upgrade() -> None:
    for key, value in MINERU_DEFAULTS:
        op.execute(
            f"""
            INSERT INTO system_settings (setting_key, value)
            VALUES ('{key}', '{value}')
            ON CONFLICT (setting_key) DO NOTHING
            """
        )


def downgrade() -> None:
    keys = ", ".join(f"'{key}'" for key, _ in MINERU_DEFAULTS)
    op.execute(f"DELETE FROM system_settings WHERE setting_key IN ({keys})")
