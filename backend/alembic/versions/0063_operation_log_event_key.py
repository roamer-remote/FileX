"""add concurrency-safe failure event identity to operation logs.

Revision ID: 0063
Revises: 0062_kb_search_trace_audit
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0063_operation_log_event_key"
down_revision: str | None = "0062_kb_search_trace_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operation_logs", sa.Column("event_key", sa.String(length=64), nullable=True))
    op.create_index("ix_operation_logs_event_key", "operation_logs", ["event_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_operation_logs_event_key", table_name="operation_logs")
    op.drop_column("operation_logs", "event_key")
