# Copyright (c) 2026 徐泽宇
"""database 模块。

Authors:
    徐泽宇
"""

import logging
import os
import time

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import (
    DATABASE_MAX_OVERFLOW,
    DATABASE_POOL_SIZE,
    DATABASE_POOL_TIMEOUT,
    DATABASE_URL,
)

logger = logging.getLogger(__name__)

engine = create_engine(
    DATABASE_URL,
    pool_size=DATABASE_POOL_SIZE,
    max_overflow=DATABASE_MAX_OVERFLOW,
    pool_timeout=DATABASE_POOL_TIMEOUT,
    pool_pre_ping=True,
    pool_recycle=1800,
)
logger.info(
    "database_pool_configured pool_size=%s max_overflow=%s pool_timeout=%s",
    DATABASE_POOL_SIZE,
    DATABASE_MAX_OVERFLOW,
    DATABASE_POOL_TIMEOUT,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """基类 类型定义。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01
    """
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def register_models() -> None:
    """注册全部 ORM 表到 metadata（worker 独立进程须先调用）。"""
    import models.user  # noqa: F401
    import models.folder  # noqa: F401
    import models.file  # noqa: F401
    import models.share_link  # noqa: F401
    import models.operation_log  # noqa: F401
    import models.api_key  # noqa: F401
    import models.system_setting  # noqa: F401
    import models.user_setting  # noqa: F401
    import models.user_ui_state  # noqa: F401
    import models.tag  # noqa: F401
    import models.file_tag_anchor  # noqa: F401
    import models.file_wiki_link  # noqa: F401
    import models.kb_log_entry  # noqa: F401
    import models.kb_chunk  # noqa: F401
    import models.kb_chunk_vector  # noqa: F401
    import models.kb_index_job  # noqa: F401
    import models.kb_correction_overlay  # noqa: F401
    import models.kb_extract_job  # noqa: F401
    import models.insavlo_webhook_event  # noqa: F401
    import models.workspace  # noqa: F401
    import models.resource_grant  # noqa: F401
    import models.file_md_version  # noqa: F401
    import models.kb_search_audit_log  # noqa: F401
    import models.kb_search_eval  # noqa: F401
    import models.kb_ragas_eval_job  # noqa: F401
    import models.gpu_scheduler  # noqa: F401
    import models.skill_file  # noqa: F401
    import models.wechat_oauth_state  # noqa: F401
    import models.wiki_compile_queue  # noqa: F401
    import models.workspace_library_report  # noqa: F401
    import models.kb_external_sync  # noqa: F401
    _register_workspace_autofill()




def _register_workspace_autofill() -> None:
    """测试与遗留路径：未显式设置 workspace_id 时回填用户个人库。"""
    from sqlalchemy import event
    from sqlalchemy.orm import object_session

    from models.file import File
    from models.folder import Folder
    from models.kb_chunk import KbChunk
    from models.tag import Tag

    def _fill_workspace(target, user_id_attr: str = "user_id") -> None:
        if getattr(target, "workspace_id", None) is not None:
            return
        uid = getattr(target, user_id_attr, None)
        if not uid:
            return
        sess = object_session(target)
        if sess is None:
            return
        from models.user import User
        from services.workspace_service import ensure_personal_workspace

        user = sess.get(User, uid)
        if user:
            target.workspace_id = ensure_personal_workspace(sess, user).id

    @event.listens_for(File, "before_insert")
    def _file_ws(mapper, connection, target):
        _fill_workspace(target)

    @event.listens_for(Folder, "before_insert")
    def _folder_ws(mapper, connection, target):
        _fill_workspace(target)

    @event.listens_for(Tag, "before_insert")
    def _tag_ws(mapper, connection, target):
        _fill_workspace(target)

    @event.listens_for(KbChunk, "before_insert")
    def _chunk_ws(mapper, connection, target):
        if target.workspace_id is not None:
            return
        sess = object_session(target)
        if sess is None:
            return
        from models.file import File as FileModel

        f = sess.get(FileModel, target.file_id)
        if f and f.workspace_id:
            target.workspace_id = f.workspace_id


def wait_for_database(
    *,
    max_attempts: int | None = None,
    interval_sec: float | None = None,
) -> None:
    """阻塞直到 PostgreSQL 可连接（容器启动顺序 / 短暂重启时避免直接崩溃）。"""
    attempts = max_attempts if max_attempts is not None else int(
        os.environ.get("FILEX_DB_WAIT_MAX_ATTEMPTS") or "60"
    )
    interval = interval_sec if interval_sec is not None else float(
        os.environ.get("FILEX_DB_WAIT_INTERVAL_SEC") or "2"
    )
    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            if i > 1:
                logger.info("database_ready after %s attempt(s)", i)
            return
        except OperationalError as exc:
            last_err = exc
            logger.warning(
                "database_not_ready attempt=%s/%s error=%s",
                i,
                attempts,
                str(exc).split("\n", 1)[0][:200],
            )
            if i < attempts:
                time.sleep(interval)
    raise RuntimeError(
        f"PostgreSQL 在 {attempts} 次尝试后仍不可用（间隔 {interval}s）"
    ) from last_err


def init_db(*, migrate: bool = True):
    """等待数据库就绪并注册 ORM；默认执行 Alembic 迁移（仅 filex API 主进程应 migrate=True）。"""
    wait_for_database()
    register_models()

    if migrate:
        alembic_ini = os.path.join(os.path.dirname(__file__), "alembic.ini")
        alembic_cfg = Config(alembic_ini)
        command.upgrade(alembic_cfg, "heads")
    try:
        with SessionLocal() as session:
            from services.kb_fts_service import ensure_zhparser_fts, zhparser_installed

            if not zhparser_installed(session):
                ensure_zhparser_fts(session)
    except Exception as exc:
        import structlog

        structlog.get_logger("filex.database").warning(
            "zhparser_fts_bootstrap_skipped", error=str(exc)
        )
