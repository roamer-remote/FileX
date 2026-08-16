"""persist terminal state needed for deterministic 187 trace selection.

Revision ID: 0064
Revises: 0063_operation_log_event_key
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0064_kb_trace_terminal"
down_revision: str | None = "0063_operation_log_event_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kb_search_audit_logs", sa.Column("status", sa.String(length=32), nullable=True))
    op.add_column("kb_search_audit_logs", sa.Column("finished_at", sa.DateTime(), nullable=True))
    op.create_index("ix_kb_search_audit_logs_status", "kb_search_audit_logs", ["status"])
    op.create_index("ix_kb_search_audit_logs_finished_at", "kb_search_audit_logs", ["finished_at"])


def downgrade() -> None:
    op.drop_index("ix_kb_search_audit_logs_finished_at", table_name="kb_search_audit_logs")
    op.drop_index("ix_kb_search_audit_logs_status", table_name="kb_search_audit_logs")
    op.drop_column("kb_search_audit_logs", "finished_at")
    op.drop_column("kb_search_audit_logs", "status")
