# Copyright (c) 2026 徐泽宇
"""license 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from datetime import datetime

from pydantic import BaseModel, Field


class LicenseStatusResponse(BaseModel):
    """授权状态响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-10

        Attributes:
            valid: 有效（bool）。
            reason: 原因（str | None）。
            expires_at: 过期时间（datetime | None）。
            customer_id: 客户ID（str | None）。
            days_remaining: daysremaining（int | None）。
            in_trial: in试用（bool）。
            license_key_masked: 授权密钥masked（str | None）。
    """
    valid: bool
    reason: str | None = None
    expires_at: datetime | None = None
    customer_id: str | None = None
    days_remaining: int | None = None
    in_trial: bool = False
    license_key_masked: str | None = Field(
        default=None,
        description="掩码后的 key 末 4 位；不返回完整 license_key",
    )


class LicenseAdminStatusResponse(LicenseStatusResponse):
    """管理端授权状态（含 HMAC 配置，仅管理员接口返回）。"""

    license_hmac_secret: str | None = Field(
        default=None,
        description="FILEX_LICENSE_HMAC_SECRET 环境变量原值；未设置时为 null",
    )
    license_hmac_secret_effective: str | None = Field(
        default=None,
        description="运行时实际用于 License 验签/签发的 HMAC secret",
    )


class LicenseActivateRequest(BaseModel):
    """授权激活请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-10

        Attributes:
            license_key: 授权密钥（str）。
            admin_username: 管理用户名（str）。
            admin_password: 管理密码（str）。
    """
    license_key: str
    admin_username: str
    admin_password: str


class LicenseAdminUpdateRequest(BaseModel):
    """授权管理更新请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            license_key: 授权密钥（str）。
    """
    license_key: str
