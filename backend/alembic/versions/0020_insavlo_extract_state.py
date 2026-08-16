"""044: Insavlo extract remote state and webhook events.

Revision ID: 0020_insavlo_extract_state
Revises: 0019_extract_bypass_cache
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020_insavlo_extract_state"
down_revision: Union[str, None] = "0019_extract_bypass_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kb_extract_jobs", sa.Column("remote_transaction_id", sa.String(length=128), nullable=True))
    op.add_column("kb_extract_jobs", sa.Column("remote_file_id", sa.String(length=128), nullable=True))
    op.add_column("kb_extract_jobs", sa.Column("remote_skill_code", sa.String(length=128), nullable=True))
    op.add_column("kb_extract_jobs", sa.Column("remote_submitted_at", sa.DateTime(), nullable=True))
    op.add_column("kb_extract_jobs", sa.Column("remote_completed_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_kb_extract_jobs_remote_transaction_id",
        "kb_extract_jobs",
        ["remote_transaction_id"],
        unique=True,
        postgresql_where=sa.text("remote_transaction_id IS NOT NULL"),
    )
    op.create_table(
        "insavlo_webhook_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("transaction_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["kb_extract_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_insavlo_webhook_events_transaction_id", "insavlo_webhook_events", ["transaction_id"], unique=True)
    op.create_index("ix_insavlo_webhook_events_job_id", "insavlo_webhook_events", ["job_id"], unique=False)
    op.create_index("ix_insavlo_webhook_events_file_id", "insavlo_webhook_events", ["file_id"], unique=False)
    op.create_index("ix_insavlo_webhook_events_status", "insavlo_webhook_events", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_insavlo_webhook_events_status", table_name="insavlo_webhook_events")
    op.drop_index("ix_insavlo_webhook_events_file_id", table_name="insavlo_webhook_events")
    op.drop_index("ix_insavlo_webhook_events_job_id", table_name="insavlo_webhook_events")
    op.drop_index("ix_insavlo_webhook_events_transaction_id", table_name="insavlo_webhook_events")
    op.drop_table("insavlo_webhook_events")
    op.drop_index("ix_kb_extract_jobs_remote_transaction_id", table_name="kb_extract_jobs")
    op.drop_column("kb_extract_jobs", "remote_completed_at")
    op.drop_column("kb_extract_jobs", "remote_submitted_at")
    op.drop_column("kb_extract_jobs", "remote_skill_code")
    op.drop_column("kb_extract_jobs", "remote_file_id")
    op.drop_column("kb_extract_jobs", "remote_transaction_id")
