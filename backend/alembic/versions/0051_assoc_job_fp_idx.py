"""Allow a changed source fingerprint within the same file generation."""
from typing import Sequence, Union

from alembic import op

revision: str = "0051_assoc_job_fp_idx"
down_revision: Union[str, None] = "0050_assoc_job_gen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0050 already creates the final fingerprint-aware index.  This revision
    # remains as a compatibility marker for databases that briefly advanced to
    # the previous 0051 implementation; it must not mutate the schema again.
    return None


def downgrade() -> None:
    return None
