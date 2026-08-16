"""0045: kb_search_eval structured RAGAS online evaluation table.

Revision ID: 0045_kb_search_eval
Revises: 0044_kb_worker_lease_fields
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045_kb_search_eval"
down_revision: Union[str, None] = "0044_kb_worker_lease_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_search_eval",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("search_trace_id", sa.String(length=64), nullable=True),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("query_preview", sa.String(length=512), nullable=False),
        sa.Column("answer_hash", sa.String(length=64), nullable=False),
        sa.Column("answer_preview", sa.String(length=512), nullable=False),
        sa.Column("context_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "context_file_ids_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "context_chunk_ids_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("faithfulness_score", sa.Float(), nullable=True),
        sa.Column("context_precision_score", sa.Float(), nullable=True),
        sa.Column("metric_provider", sa.String(length=32), server_default="ragas", nullable=False),
        sa.Column("metric_version", sa.String(length=255), nullable=True),
        sa.Column("metric_variant", sa.String(length=255), nullable=True),
        sa.Column("llm_provider", sa.String(length=64), nullable=True),
        sa.Column("llm_model", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_search_eval_id", "kb_search_eval", ["id"])
    op.create_index("ix_kb_search_eval_user_id", "kb_search_eval", ["user_id"])
    op.create_index("ix_kb_search_eval_workspace_id", "kb_search_eval", ["workspace_id"])
    op.create_index("ix_kb_search_eval_agent_run_id", "kb_search_eval", ["agent_run_id"])
    op.create_index("ix_kb_search_eval_search_trace_id", "kb_search_eval", ["search_trace_id"])
    op.create_index("ix_kb_search_eval_query_hash", "kb_search_eval", ["query_hash"])
    op.create_index("ix_kb_search_eval_answer_hash", "kb_search_eval", ["answer_hash"])
    op.create_index("ix_kb_search_eval_status", "kb_search_eval", ["status"])
    op.create_index("ix_kb_search_eval_created_at", "kb_search_eval", ["created_at"])
    op.create_index("ix_kb_search_eval_evaluated_at", "kb_search_eval", ["evaluated_at"])


def downgrade() -> None:
    op.drop_index("ix_kb_search_eval_evaluated_at", table_name="kb_search_eval")
    op.drop_index("ix_kb_search_eval_created_at", table_name="kb_search_eval")
    op.drop_index("ix_kb_search_eval_status", table_name="kb_search_eval")
    op.drop_index("ix_kb_search_eval_answer_hash", table_name="kb_search_eval")
    op.drop_index("ix_kb_search_eval_query_hash", table_name="kb_search_eval")
    op.drop_index("ix_kb_search_eval_search_trace_id", table_name="kb_search_eval")
    op.drop_index("ix_kb_search_eval_agent_run_id", table_name="kb_search_eval")
    op.drop_index("ix_kb_search_eval_workspace_id", table_name="kb_search_eval")
    op.drop_index("ix_kb_search_eval_user_id", table_name="kb_search_eval")
    op.drop_index("ix_kb_search_eval_id", table_name="kb_search_eval")
    op.drop_table("kb_search_eval")
