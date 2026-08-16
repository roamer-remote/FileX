# Copyright (c) 2026 徐泽宇
"""kb_extract_job 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func

from database import Base


class KbExtractJob(Base):
    """资料库提取任务 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-31

        Attributes:
            id: ID数据库列。
            user_id: 用户ID数据库列。
            file_id: 文件ID数据库列。
            status: 状态数据库列。
            provider: 提供者数据库列。
            attempts: attempts数据库列。
            last_error: last错误数据库列。
            created_at: 创建时间数据库列。
            updated_at: 更新时间数据库列。
    """
    __tablename__ = "kb_extract_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(16), nullable=False, server_default="queued")
    provider = Column(String(16), nullable=True)
    bypass_mineru_cache = Column(Boolean, nullable=False, server_default="false")
    remote_transaction_id = Column(String(128), nullable=True, unique=True)
    remote_file_id = Column(String(128), nullable=True)
    remote_skill_code = Column(String(128), nullable=True)
    remote_submitted_at = Column(DateTime, nullable=True)
    remote_completed_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, server_default="0")
    oom_retry_count = Column(Integer, nullable=False, server_default="0")
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
