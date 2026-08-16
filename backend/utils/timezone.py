# Copyright (c) 2026 徐泽宇
"""时间展示：库内 naive 时间按北京时间（与 compose TZ=Asia/Shanghai 一致）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> datetime:
    """当前北京时间（带时区）。"""
    return datetime.now(BEIJING_TZ)


def naive_db_now() -> datetime:
    """与 PostgreSQL func.now() 在 TZ=Asia/Shanghai 下写入的 naive 时间对齐。"""
    return beijing_now().replace(tzinfo=None)


def to_beijing_time(dt: datetime | None) -> datetime | None:
    """将 datetime 转为北京时间用于 API 展示。

    - naive：视为数据库/服务端已写入的北京时间（PostgreSQL func.now() 在 Asia/Shanghai 下）
    - aware：按其时区换算到北京
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BEIJING_TZ)
    return dt.astimezone(BEIJING_TZ)
