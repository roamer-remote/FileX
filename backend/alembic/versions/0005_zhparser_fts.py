"""008: zhparser extension and zh_cn text search configuration

Revision ID: 0005_zhparser_fts
Revises: 0004_kb_extract_job_provider
Create Date: 2026-05-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_zhparser_fts"
down_revision: Union[str, None] = "0004_kb_extract_job_provider"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _zhparser_available(connection) -> bool:
    row = connection.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'zhparser' LIMIT 1")
    ).first()
    return row is not None


def _zhparser_parser_ready(connection) -> bool:
    """TEXT SEARCH PARSER 名为 zhparser（见 zhparser--2.3.sql），非 zhparser.zhparser。"""
    row = connection.execute(
        sa.text("SELECT 1 FROM pg_ts_parser WHERE prsname = 'zhparser' LIMIT 1")
    ).first()
    return row is not None


def upgrade() -> None:
    conn = op.get_bind()
    if not _zhparser_available(conn):
        # 开发/CI 未换镜像时先跳过；换 filex-postgres:pg16-zh 后由 init_db.ensure_zhparser_fts 补齐
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS zhparser")
    if not _zhparser_parser_ready(conn):
        return
    op.execute(
        """
        DO $do$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'zh_cn') THEN
            CREATE TEXT SEARCH CONFIGURATION zh_cn (PARSER = zhparser);
            ALTER TEXT SEARCH CONFIGURATION zh_cn
              ADD MAPPING FOR n,v,a,i,e,l,j WITH simple;
          END IF;
        END
        $do$;
        """
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not _zhparser_available(conn):
        return
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS zh_cn")
    op.execute("DROP EXTENSION IF EXISTS zhparser")
