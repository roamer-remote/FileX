# Copyright (c) 2026 徐泽宇
"""kb_log_entry 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.sql import func

from database import Base


class KbLogEntry(Base):
    """资料库日志条目 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-01

        Attributes:
            id: ID数据库列。
            user_id: 用户ID数据库列。
            workspace_id: 知识空间ID数据库列。
            entry: 条目数据库列。
            created_at: 创建时间数据库列。
    """
    __tablename__ = "kb_log_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    entry = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
