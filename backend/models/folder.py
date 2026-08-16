# Copyright (c) 2026 徐泽宇
"""folder 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from database import Base


class Folder(Base):
    """文件夹 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            id: ID数据库列。
            name: 名称数据库列。
            parent_id: 父级ID数据库列。
            workspace_id: 知识空间ID数据库列。
            user_id: 用户ID数据库列。
            created_at: 创建时间数据库列。
    """
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
