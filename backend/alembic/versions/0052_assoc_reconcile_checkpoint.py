"""Persist workspace association reconcile cursors."""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0052_assoc_reconcile_cursor"
down_revision: Union[str, None] = "0051_assoc_job_fp_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_association_reconcile_checkpoints",
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("cursor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("status", sa.String(16), server_default="running", nullable=False),
        sa.Column("last_error", sa.String(2000), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id"),
    )


def downgrade() -> None:
    op.drop_table("kb_association_reconcile_checkpoints")
