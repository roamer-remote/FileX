"""Add repeatable scan rounds to association reconcile checkpoints.

Revision ID: 0053_assoc_reconcile_round
Revises: 0052_assoc_reconcile_cursor
"""

from alembic import op
import sqlalchemy as sa

revision = "0053_assoc_reconcile_round"
down_revision = "0052_assoc_reconcile_cursor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kb_association_reconcile_checkpoints",
        sa.Column("scan_round", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("kb_association_reconcile_checkpoints", "scan_round")
