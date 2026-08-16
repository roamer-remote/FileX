# Copyright (c) 2026 徐泽宇
"""kb_index_job 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func

from database import Base


class KbIndexJob(Base):
    """资料库索引任务 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-18

        Attributes:
            id: ID数据库列。
            user_id: 用户ID数据库列。
            file_id: 文件ID数据库列。
            status: 状态数据库列。
            attempts: attempts数据库列。
            last_error: last错误数据库列。
            force: 强制全量重建索引（047）。
            created_at: 创建时间数据库列。
            updated_at: 更新时间数据库列。
    """
    __tablename__ = "kb_index_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(16), nullable=False, server_default="queued")
    attempts = Column(Integer, nullable=False, server_default="0")
    last_error = Column(Text, nullable=True)
    force = Column(Boolean, nullable=False, server_default="false")
    heartbeat_at = Column(DateTime, nullable=True)
    worker_id = Column(String(128), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    lease_generation = Column(Integer, nullable=False, server_default="0")
    correction_overlay_id = Column(
        Integer,
        ForeignKey("kb_correction_overlays.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_key = Column(String(256), nullable=True, unique=True, index=True)
    strategy_id = Column(String(32), nullable=True, index=True)
    strategy_version = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
