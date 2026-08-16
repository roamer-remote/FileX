"""144 association job generation and source fingerprint."""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0050_assoc_job_gen"
down_revision: Union[str, None] = "0049_kb_association_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("kb_association_jobs", sa.Column("workspace_id", sa.Integer(), nullable=True))
    op.add_column("kb_association_jobs", sa.Column("source_fingerprint", sa.String(64), nullable=True))
    op.add_column("kb_association_jobs", sa.Column("generation", sa.Integer(), server_default="0", nullable=False))
    op.execute("UPDATE kb_association_jobs j SET workspace_id=f.workspace_id, source_fingerprint=COALESCE(f.index_source_hash, f.md_content_hash, '') FROM files f WHERE f.id=j.file_id")
    op.alter_column("kb_association_jobs", "workspace_id", nullable=False)
    op.alter_column("kb_association_jobs", "source_fingerprint", nullable=False)
    op.create_foreign_key("fk_kb_association_jobs_workspace", "kb_association_jobs", "workspaces", ["workspace_id"], ["id"], ondelete="CASCADE")
    op.create_index(
        "uq_kb_association_jobs_file_generation",
        "kb_association_jobs",
        ["file_id", "generation", "source_fingerprint"],
        unique=True,
    )

def downgrade() -> None:
    op.drop_index("uq_kb_association_jobs_file_generation", table_name="kb_association_jobs")
    op.drop_constraint("fk_kb_association_jobs_workspace", "kb_association_jobs", type_="foreignkey")
    op.drop_column("kb_association_jobs", "generation")
    op.drop_column("kb_association_jobs", "source_fingerprint")
    op.drop_column("kb_association_jobs", "workspace_id")
