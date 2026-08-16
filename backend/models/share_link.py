# Copyright (c) 2026 徐泽宇
"""share_link 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from database import Base


class ShareLink(Base):
    """分享链接 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-08

        Attributes:
            id: ID数据库列。
            file_id: 文件ID数据库列。
            token: 令牌数据库列。
            password_hash: 密码哈希数据库列。
            expires_at: 过期时间数据库列。
            max_downloads: 最大downloads数据库列。
            download_count: 下载数量数据库列。
            created_by: 创建by数据库列。
            created_at: 创建时间数据库列。
    """
    __tablename__ = "share_links"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    max_downloads = Column(Integer, nullable=True)
    download_count = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
