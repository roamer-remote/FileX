# Copyright (c) 2026 徐泽宇
"""operation_log 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func

from database import Base


class OperationLog(Base):
    """操作日志 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            id: ID数据库列。
            user_id: 用户ID数据库列。
            action: 动作数据库列。
            target_type: 目标类型数据库列。
            target_id: 目标ID数据库列。
            detail: 详情数据库列。
            created_at: 创建时间数据库列。
    """
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)
    target_type = Column(String(50), nullable=True)
    target_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)
    event_key = Column(String(64), nullable=True, unique=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
