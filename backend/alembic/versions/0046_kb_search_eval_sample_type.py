"""0046: kb_search_eval.sample_type — 区分正常回答样本与召回质量样本。

Revision ID: 0046_kb_search_eval_sample_type
Revises: 0045_kb_search_eval
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0046_kb_search_eval_sample_type"
down_revision: Union[str, None] = "0045_kb_search_eval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kb_search_eval",
        sa.Column(
            "sample_type",
            sa.String(length=32),
            nullable=False,
            server_default="answer",
        ),
    )
    op.create_index(
        "ix_kb_search_eval_sample_type",
        "kb_search_eval",
        ["sample_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_kb_search_eval_sample_type", table_name="kb_search_eval")
    op.drop_column("kb_search_eval", "sample_type")
