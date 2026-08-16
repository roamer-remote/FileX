"""142: durable RAGAS evaluation queue and diagnostics.

Revision ID: 0047_kb_ragas_eval_queue
Revises: 0046_kb_search_eval_sample_type
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047_kb_ragas_eval_queue"
down_revision: Union[str, None] = "0046_kb_search_eval_sample_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kb_search_eval", sa.Column("queue_duration_ms", sa.Integer(), nullable=True))
    op.add_column(
        "kb_search_eval", sa.Column("faithfulness_duration_ms", sa.Integer(), nullable=True)
    )
    op.add_column(
        "kb_search_eval", sa.Column("context_precision_duration_ms", sa.Integer(), nullable=True)
    )
    op.add_column(
        "kb_search_eval", sa.Column("failure_stage", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "kb_search_eval", sa.Column("context_budget_version", sa.String(length=16), nullable=True)
    )
    op.add_column("kb_search_eval", sa.Column("source_context_count", sa.Integer(), nullable=True))
    op.add_column("kb_search_eval", sa.Column("selected_context_count", sa.Integer(), nullable=True))
    op.add_column("kb_search_eval", sa.Column("selected_context_chars", sa.Integer(), nullable=True))
    op.create_index(
        "ix_kb_search_eval_failure_stage", "kb_search_eval", ["failure_stage"], unique=False
    )

    op.create_table(
        "kb_ragas_eval_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("eval_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("queued_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("evaluation_deadline_at", sa.DateTime(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_stage", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["eval_id"], ["kb_search_eval.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eval_id", name="uq_kb_ragas_eval_jobs_eval_id"),
    )
    op.create_index("ix_kb_ragas_eval_jobs_eval_id", "kb_ragas_eval_jobs", ["eval_id"])
    op.create_index("ix_kb_ragas_eval_jobs_status", "kb_ragas_eval_jobs", ["status"])
    op.create_index("ix_kb_ragas_eval_jobs_queued_at", "kb_ragas_eval_jobs", ["queued_at"])
    op.create_index(
        "ix_kb_ragas_eval_jobs_lease_expires_at",
        "kb_ragas_eval_jobs",
        ["lease_expires_at"],
    )
    op.create_index(
        "ix_kb_ragas_eval_jobs_claim",
        "kb_ragas_eval_jobs",
        ["status", "queued_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_kb_ragas_eval_jobs_claim", table_name="kb_ragas_eval_jobs")
    op.drop_index("ix_kb_ragas_eval_jobs_lease_expires_at", table_name="kb_ragas_eval_jobs")
    op.drop_index("ix_kb_ragas_eval_jobs_queued_at", table_name="kb_ragas_eval_jobs")
    op.drop_index("ix_kb_ragas_eval_jobs_status", table_name="kb_ragas_eval_jobs")
    op.drop_index("ix_kb_ragas_eval_jobs_eval_id", table_name="kb_ragas_eval_jobs")
    op.drop_table("kb_ragas_eval_jobs")

    op.drop_index("ix_kb_search_eval_failure_stage", table_name="kb_search_eval")
    op.drop_column("kb_search_eval", "selected_context_chars")
    op.drop_column("kb_search_eval", "selected_context_count")
    op.drop_column("kb_search_eval", "source_context_count")
    op.drop_column("kb_search_eval", "context_budget_version")
    op.drop_column("kb_search_eval", "failure_stage")
    op.drop_column("kb_search_eval", "context_precision_duration_ms")
    op.drop_column("kb_search_eval", "faithfulness_duration_ms")
    op.drop_column("kb_search_eval", "queue_duration_ms")
