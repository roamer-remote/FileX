"""persist bounded retrieval trace envelopes for 187-P1.

Revision ID: 0062
Revises: 0061_gpu_scheduler_state
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0062_kb_search_trace_audit"
down_revision: str | None = "0061_gpu_scheduler_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kb_search_audit_logs", sa.Column("trace_id", sa.String(length=64), nullable=True))
    op.add_column("kb_search_audit_logs", sa.Column("request_scope", sa.String(length=64), nullable=True))
    op.add_column("kb_search_audit_logs", sa.Column("query_hash", sa.String(length=16), nullable=True))
    op.add_column("kb_search_audit_logs", sa.Column("trace_payload", sa.Text(), nullable=True))
    op.create_index("ix_kb_search_audit_logs_trace_id", "kb_search_audit_logs", ["trace_id"])
    op.create_index("ix_kb_search_audit_logs_request_scope", "kb_search_audit_logs", ["request_scope"])
    op.create_index("ix_kb_search_audit_logs_query_hash", "kb_search_audit_logs", ["query_hash"])


def downgrade() -> None:
    op.drop_index("ix_kb_search_audit_logs_query_hash", table_name="kb_search_audit_logs")
    op.drop_index("ix_kb_search_audit_logs_request_scope", table_name="kb_search_audit_logs")
    op.drop_index("ix_kb_search_audit_logs_trace_id", table_name="kb_search_audit_logs")
    op.drop_column("kb_search_audit_logs", "trace_payload")
    op.drop_column("kb_search_audit_logs", "query_hash")
    op.drop_column("kb_search_audit_logs", "request_scope")
    op.drop_column("kb_search_audit_logs", "trace_id")
