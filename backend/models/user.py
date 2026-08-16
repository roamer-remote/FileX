# Copyright (c) 2026 徐泽宇
"""user 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, DateTime, LargeBinary, text
from sqlalchemy.orm import deferred
from sqlalchemy.sql import func

from database import Base


class User(Base):
    """用户 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-07

        Attributes:
            id: ID数据库列。
            username: 用户名数据库列。
            password_hash: 密码哈希数据库列。
            is_admin: 是否管理数据库列。
            is_active: 是否启用数据库列。
            created_at: 创建时间数据库列。
            last_login_at: last登录时间数据库列。
            password_rev: 密码版本号数据库列。
            wechat_openid: 微信OpenID数据库列。
            wechat_unionid: 微信UnionID数据库列。
            wechat_nickname: 微信昵称数据库列。
            avatar_mime: 头像MIME数据库列。
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at = Column(DateTime, server_default=func.now())
    last_login_at = Column(DateTime, nullable=True)
    # 递增后使此前签发的 JWT 全部失效（与 JWT 内 pwd_rev 比对）
    password_rev = Column(Integer, nullable=False, default=0, server_default="0")
    wechat_openid = Column(String(64), unique=True, nullable=True, index=True)
    wechat_unionid = Column(String(64), nullable=True)
    wechat_nickname = Column(String(128), nullable=True)
    avatar_mime = Column(String(80), nullable=True)
    avatar_data = deferred(Column(LargeBinary(), nullable=True))
    primary_department_id = Column(
        Integer,
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
