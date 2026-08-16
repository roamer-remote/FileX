# Copyright (c) 2026 徐泽宇
"""file_md_version 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.sql import func

from database import Base


class FileMdVersion(Base):
    """文件Markdown版本 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            id: ID数据库列。
            file_id: 文件ID数据库列。
            version: 版本数据库列。
            content: 内容数据库列。
            created_by_user_id: 创建by用户ID数据库列。
            created_at: 创建时间数据库列。
    """
    __tablename__ = "file_md_versions"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
