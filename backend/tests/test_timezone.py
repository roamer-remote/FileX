# Copyright (c) 2026 徐泽宇
"""时区：避免 naive 北京时间被当作 UTC 再加 8 小时。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from datetime import datetime, timezone

from utils.timezone import BEIJING_TZ, to_beijing_time


def test_naive_datetime_treated_as_beijing_wall_time():
    """Docker/Postgres TZ=Asia/Shanghai 写入的 naive 值不再 +8。"""
    naive = datetime(2026, 5, 23, 21, 30, 0)
    out = to_beijing_time(naive)
    assert out is not None
    assert out.tzinfo == BEIJING_TZ
    assert out.hour == 21
    assert out.day == 23
    assert "+08:00" in out.isoformat()


def test_utc_aware_converts_to_beijing():
    aware_utc = datetime(2026, 5, 23, 13, 30, 0, tzinfo=timezone.utc)
    out = to_beijing_time(aware_utc)
    assert out is not None
    assert out.hour == 21
    assert out.day == 23

def test_record_user_login_writes_beijing_naive(db_session):
    """登录时间写入应与 created_at 同为北京时间墙钟。"""
    from datetime import datetime
    from unittest.mock import patch

    from models.user import User
    from services.auth_service import create_user, record_user_login

    user = create_user(db_session, "tz_login_user", "pass12345", is_admin=False)
    fixed = datetime(2026, 5, 26, 15, 9, 17, tzinfo=BEIJING_TZ)
    with patch("utils.timezone.beijing_now", return_value=fixed):
        record_user_login(db_session, user)
    db_session.refresh(user)
    assert user.last_login_at == datetime(2026, 5, 26, 15, 9, 17)
    shown = to_beijing_time(user.last_login_at)
    assert shown is not None
    assert shown.hour == 15

