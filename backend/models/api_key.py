# Copyright (c) 2026 徐泽宇
"""api_key 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func

from database import Base


class ApiKey(Base):
    """API密钥 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-02

        Attributes:
            id: ID数据库列。
            key_hash: 密钥哈希数据库列。
            key_secret_encrypted: 密钥密钥encrypted数据库列。
            name: 名称数据库列。
            prefix: 前缀数据库列。
            user_id: 用户ID数据库列。
            is_active: 是否启用数据库列。
            created_at: 创建时间数据库列。
            last_used_at: lastused时间数据库列。
    """
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key_hash = Column(String(128), nullable=False)
    key_secret_encrypted = Column(Text, nullable=True)
    name = Column(String(100), nullable=False)
    prefix = Column(String(8), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    last_used_at = Column(DateTime, nullable=True)
