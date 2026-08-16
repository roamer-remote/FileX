"""Add durable GPU scheduler lease and route outbox tables (164 T-3)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0058_gpu_scheduler_lease_outbox"
down_revision: Union[str, None] = "0057_kb_multi_repr_enabled_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gpu_scheduler_leases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gpu_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("fencing_token", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=False),
        sa.Column("active_job_id", sa.String(length=128), nullable=True),
        sa.Column("release_ack_at", sa.DateTime(), nullable=True),
        sa.Column("watchdog_empty_confirmations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_watchdog_at", sa.DateTime(), nullable=True),
        sa.Column("handover_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("gpu_id", name="uq_gpu_scheduler_leases_gpu_id"),
    )
    op.create_index("ix_gpu_scheduler_leases_gpu_id", "gpu_scheduler_leases", ["gpu_id"])
    op.create_table(
        "gpu_scheduler_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_kind", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("handover_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("acked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_gpu_scheduler_outbox_idempotency_key"),
    )
    op.create_index("ix_gpu_scheduler_outbox_job_id", "gpu_scheduler_outbox", ["job_id"])
    op.create_index("ix_gpu_scheduler_outbox_file_id", "gpu_scheduler_outbox", ["file_id"])
    op.create_index("ix_gpu_scheduler_outbox_state", "gpu_scheduler_outbox", ["state"])


def downgrade() -> None:
    op.drop_index("ix_gpu_scheduler_outbox_state", table_name="gpu_scheduler_outbox")
    op.drop_index("ix_gpu_scheduler_outbox_file_id", table_name="gpu_scheduler_outbox")
    op.drop_index("ix_gpu_scheduler_outbox_job_id", table_name="gpu_scheduler_outbox")
    op.drop_table("gpu_scheduler_outbox")
    op.drop_index("ix_gpu_scheduler_leases_gpu_id", table_name="gpu_scheduler_leases")
    op.drop_table("gpu_scheduler_leases")
