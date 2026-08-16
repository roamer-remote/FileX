# Copyright (c) 2026 徐泽宇
"""auth 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-08

        Attributes:
            username: 用户名（str）。
            password: 密码（str）。
    """
    username: str
    password: str


class RegisterRequest(BaseModel):
    """注册请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            username: 用户名（str）。
            password: 密码（str）。
            wechat_state: 微信状态（str | None）。
    """
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    wechat_state: str | None = Field(default=None, max_length=36)


class TokenResponse(BaseModel):
    """令牌响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            access_token: access令牌（str）。
            token_type: 令牌类型（str）。
    """
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """用户响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-31

        Attributes:
            id: ID（int）。
            username: 用户名（str）。
            is_admin: 是否管理（bool）。
            is_active: 是否启用（bool）。
            created_at: 创建时间（str）。
            has_avatar: 拥有头像（bool）。
            wechat_bound: 微信绑定（bool）。
    """
    id: int
    username: str
    is_admin: bool
    is_active: bool
    created_at: str
    has_avatar: bool = False
    wechat_bound: bool = False

    class Config:
        """Pydantic 模型配置。

            Authors:
                徐泽宇

            Copyright:
                © 2026 徐泽宇

            Attributes:
                from_attributes: fromattributes常量。
        """
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    """修改密码请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            current_password: current密码（str）。
            new_password: new密码（str）。
    """
    current_password: str = Field(..., min_length=1, max_length=100)
    new_password: str = Field(..., min_length=6, max_length=100)
