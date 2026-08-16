"""107 agent run trace tables.

Revision ID: 0039_agent_runs
Revises: 0038_share_expires_at_beijing
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039_agent_runs"
down_revision: Union[str, None] = "0038_share_expires_at_beijing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("api_key_id", sa.Integer(), nullable=True),
        sa.Column("thread_id", sa.String(length=128), nullable=True),
        sa.Column("question_preview", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_user_started", "agent_runs", ["user_id", "started_at"])
    op.create_index(op.f("ix_agent_runs_thread_id"), "agent_runs", ["thread_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_expires_at"), "agent_runs", ["expires_at"], unique=False)

    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("client_event_id", sa.String(length=36), nullable=True),
        sa.Column("parent_seq", sa.Integer(), nullable=True),
        sa.Column("task_key", sa.String(length=128), nullable=True),
        sa.Column("span_id", sa.String(length=36), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ts", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("layer", sa.String(length=16), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("meta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "client_event_id", name="uq_agent_run_events_run_client"),
        sa.UniqueConstraint("run_id", "seq", name="uq_agent_run_events_run_seq"),
    )
    op.create_index(op.f("ix_agent_run_events_run_id"), "agent_run_events", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_run_events_run_id"), table_name="agent_run_events")
    op.drop_table("agent_run_events")
    op.drop_index(op.f("ix_agent_runs_expires_at"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_thread_id"), table_name="agent_runs")
    op.drop_index("ix_agent_runs_user_started", table_name="agent_runs")
    op.drop_table("agent_runs")
