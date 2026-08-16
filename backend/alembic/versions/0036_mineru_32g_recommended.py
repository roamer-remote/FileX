"""Publish 32G MinerU recommended settings into system_settings.

This ensures that on production deploy (after alembic upgrade head),
the MinerU pipeline uses the 32G-tuned defaults automatically,
without requiring manual update via /admin/settings.

Revision ID: 0036_mineru_32g_recommended
Revises: 0035_kb_sag_events
"""

from typing import Sequence, Union

from alembic import op

# Recommended values for 32G production MinerU allocation (mem_limit 32g, shm 8gb)
RECOMMENDED = {
    "mineru_min_batch_mode": "auto",
    "mineru_min_batch_inference_size": "112",
    "mineru_min_batch_floor": "16",
    "mineru_page_chunk_enabled": "true",
    "mineru_page_chunk_threshold": "160",
    "mineru_page_chunk_pages": "64",
    "mineru_parse_timeout_sec": "1200",
    "mineru_rpc_timeout_sec": "3600",
}

revision: str = "0036_mineru_32g_recommended"
down_revision: Union[str, None] = "0035_kb_sag_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for key, value in RECOMMENDED.items():
        op.execute(
            f"UPDATE system_settings SET value = '{value}' "
            f"WHERE setting_key = '{key}'"
        )


def downgrade() -> None:
    # Downgrade is a no-op for these recommended values.
    # Previous values are not restored because they were environment-specific.
    pass
