"""Track MinerU batch residence state on GPU lease (164 T-4)."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0059_gpu_scheduler_lease_batch"
down_revision: Union[str, None] = "0058_gpu_scheduler_lease_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gpu_scheduler_leases",
        sa.Column("model_group", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "gpu_scheduler_leases",
        sa.Column("batch_started_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "gpu_scheduler_leases",
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("gpu_scheduler_leases", "batch_size")
    op.drop_column("gpu_scheduler_leases", "batch_started_at")
    op.drop_column("gpu_scheduler_leases", "model_group")
