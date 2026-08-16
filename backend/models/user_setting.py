# Copyright (c) 2026 徐泽宇
"""user_setting 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint

from database import Base


class UserSetting(Base):
    """用户资料库偏好 sparse override。"""

    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", "setting_key", name="uq_user_settings_user_key"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    setting_key = Column(String(64), nullable=False)
    value = Column(Text, nullable=False, default="")
