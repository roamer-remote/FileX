# Copyright (c) 2026 徐泽宇
"""system_setting 相关 ORM 模型模块。

Authors:
    徐泽宇
"""

from sqlalchemy import Column, Integer, String, Text

from database import Base


class SystemSetting(Base):
    """system设置 ORM 数据库模型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            id: ID数据库列。
            setting_key: 设置密钥数据库列。
            value: value数据库列。
    """
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(64), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False, default="")
