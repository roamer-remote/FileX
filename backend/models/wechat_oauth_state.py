# Copyright (c) 2026 徐泽宇
"""wechat_oauth_state 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func

from database import Base


class WeChatOAuthState(Base):
    """wechato认证状态 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-31

        Attributes:
            state: 状态数据库列。
            mode: mode数据库列。
            status: 状态数据库列。
            bind_user_id: bind用户ID数据库列。
            success_user_id: success用户ID数据库列。
            pending_openid: 待处理OpenID数据库列。
            pending_unionid: 待处理UnionID数据库列。
            pending_nickname: 待处理昵称数据库列。
            created_at: 创建时间数据库列。
            expires_at: 过期时间数据库列。
            consumed_at: consumed时间数据库列。
    """
    __tablename__ = "wechat_oauth_states"

    state = Column(String(36), primary_key=True)
    mode = Column(String(16), nullable=False, server_default="login")
    status = Column(String(32), nullable=False, server_default="pending")
    bind_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    success_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    pending_openid = Column(String(64), nullable=True)
    pending_unionid = Column(String(64), nullable=True)
    pending_nickname = Column(String(128), nullable=True)
    poll_secret = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
