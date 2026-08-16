# Copyright (c) 2026 徐泽宇
"""env 模块。

Authors:
    徐泽宇
"""

import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy import create_engine

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 从环境变量读取数据库 URL，默认使用 config.py 中的配置
from config import DATABASE_URL as APP_DATABASE_URL

# 勿 set_main_option：URL 密码含 % 时 ConfigParser 会报 invalid interpolation
database_url = os.environ.get("DATABASE_URL") or APP_DATABASE_URL

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from database import Base
from models.user import User  # noqa: F401
from models.folder import Folder  # noqa: F401
from models.file import File  # noqa: F401
from models.share_link import ShareLink  # noqa: F401
from models.kb_search_audit_log import KbSearchAuditLog  # noqa: F401
from models.file_md_version import FileMdVersion  # noqa: F401
from models.resource_grant import ResourceGrant  # noqa: F401
from models.workspace import Workspace, WorkspaceMember  # noqa: F401
from models.operation_log import OperationLog  # noqa: F401
from models.api_key import ApiKey  # noqa: F401
from models.tag import Tag  # noqa: F401
from models.skill_file import SkillFile, SkillFileRevision  # noqa: F401
from models.kb_doc_entity_edge import KbDocEntityEdge  # noqa: F401
from models.kb_event import KbEvent  # noqa: F401
from models.kb_event_entity import KbEventEntity  # noqa: F401
from models.kb_search_eval import KbSearchEval  # noqa: F401
from models.kb_ragas_eval_job import KbRagasEvalJob  # noqa: F401
from models.kb_association import (  # noqa: F401
    KbAssociationIndexState,
    KbEntity,
    KbEntityAlias,
    KbEntityMention,
    KbEvidenceClaim,
)
from models.kb_association_job import KbAssociationJob  # noqa: F401
from models.kb_association_reconcile import KbAssociationReconcileCheckpoint  # noqa: F401
from models.gpu_scheduler import GpuSchedulerState  # noqa: F401

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_engine(database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
