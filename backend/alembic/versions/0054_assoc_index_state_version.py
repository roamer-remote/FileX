"""Persist association extractor/content versions for bounded coverage aggregation.

Revision ID: 0054_assoc_state_version
Revises: 0053_assoc_reconcile_round
"""

from alembic import op
import sqlalchemy as sa


revision = "0054_assoc_state_version"
down_revision = "0053_assoc_reconcile_round"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kb_association_index_state",
        sa.Column("extractor_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "kb_association_index_state",
        sa.Column("content_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("kb_association_index_state", "content_fingerprint")
    op.drop_column("kb_association_index_state", "extractor_version")
