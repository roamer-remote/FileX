# Copyright (c) 2026 徐泽宇
"""share 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from pydantic import BaseModel, Field
from typing import Optional


class CreateShareRequest(BaseModel):
    """创建分享请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            file_id: 文件ID（int）。
            expires_in_hours: 过期inhours（Optional[int]）。
            password: 密码（Optional[str]）。
            max_downloads: 最大downloads（Optional[int]）。
    """
    file_id: int
    expires_in_hours: Optional[int] = Field(default=None, ge=1, le=720)
    password: Optional[str] = Field(default=None, max_length=100)
    max_downloads: Optional[int] = Field(default=None, ge=1)


class CreateShareResponse(BaseModel):
    """创建分享响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            token: 令牌（str）。
            url: URL（str）。
    """
    token: str
    url: str


class ShareInfoResponse(BaseModel):
    """分享信息响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-08

        Attributes:
            id: ID（int）。
            token: 令牌（str）。
            file_id: 文件ID（int）。
            file_name: 文件名称（str）。
            file_size: 文件大小（int）。
            mime_type: MIME类型（str）。
            expires_at: 过期时间（Optional[str]）。
            has_password: 拥有密码（bool）。
            max_downloads: 最大downloads（Optional[int]）。
            download_count: 下载数量（int）。
            created_at: 创建时间（str）。
    """
    id: int
    token: str
    file_id: int
    file_name: str
    file_size: int
    mime_type: str
    expires_at: Optional[str] = None
    has_password: bool
    max_downloads: Optional[int] = None
    download_count: int
    created_at: str

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


class VerifyPasswordRequest(BaseModel):
    """校验密码请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            password: 密码（str）。
    """
    password: str
