# Copyright (c) 2026 徐泽宇
"""admin 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from pydantic import BaseModel, Field


class AdminCreateUserRequest(BaseModel):
    """管理创建用户请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            username: 用户名（str）。
            password: 密码（str）。
            is_admin: 是否管理（bool）。
    """
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    is_admin: bool = False
