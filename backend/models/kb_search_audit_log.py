# Copyright (c) 2026 徐泽宇
"""kb_search_audit_log 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from database import Base


class KbSearchAuditLog(Base):
    """资料库检索审计日志 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            id: ID数据库列。
            user_id: 用户ID数据库列。
            workspace_id: 知识空间ID数据库列。
            query: query数据库列。
            hit_file_ids: hit文件ids数据库列。
            top_k: topk数据库列。
            created_at: 创建时间数据库列。
    """
    __tablename__ = "kb_search_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    query = Column(Text, nullable=False)
    hit_file_ids = Column(Text, nullable=True)
    top_k = Column(Integer, nullable=False, server_default="8")
    trace_id = Column(String(64), nullable=True, index=True)
    request_scope = Column(String(64), nullable=True, index=True)
    query_hash = Column(String(16), nullable=True, index=True)
    trace_payload = Column(Text, nullable=True)
    status = Column(String(32), nullable=True, index=True)
    finished_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
