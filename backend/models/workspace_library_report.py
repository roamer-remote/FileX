# Copyright (c) 2026 徐泽宇
"""workspace_library_report 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from database import Base


class WorkspaceLibraryReport(Base):
    """知识空间资料库报告 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            id: ID数据库列。
            workspace_id: 知识空间ID数据库列。
            status: 状态数据库列。
            generated_at: generated时间数据库列。
            payload_json: 载荷json数据库列。
            error_message: 错误消息数据库列。
            triggered_by_user_id: triggeredby用户ID数据库列。
            created_at: 创建时间数据库列。
            updated_at: 更新时间数据库列。
    """
    __tablename__ = "workspace_library_reports"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="pending")
    generated_at = Column(DateTime(timezone=True), nullable=True)
    payload_json = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    triggered_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
