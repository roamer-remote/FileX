# Copyright (c) 2026 徐泽宇
"""Tests for license_cache_service (fakeredis).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import json

import pytest

fakeredis = pytest.importorskip("fakeredis")

from models.system_setting import SystemSetting
from services.license_cache_service import STATUS_KEY, get_cached_status, invalidate_license_cache, warm_license_cache
from services.license_service import KEY_LICENSE_KEY, build_license_key
from utils.timezone import BEIJING_TZ
from datetime import datetime

TEST_SECRET = "cache-test-hmac-secret"


@pytest.fixture(autouse=True)
def _license_cache_env(monkeypatch):
    monkeypatch.setenv("FILEX_LICENSE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.delenv("FILEX_ENV", raising=False)
    import importlib

    import config

    importlib.reload(config)
    monkeypatch.setattr("services.license_cache_service.REDIS_URL", "redis://fake")
    yield
    invalidate_license_cache()


@pytest.fixture
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    from services import license_cache_service as cache

    monkeypatch.setattr(cache, "_get_client", lambda: fake)
    monkeypatch.setattr(cache, "enabled", lambda: True)
    return fake


def _valid_key() -> str:
    exp = datetime(2030, 12, 31, 23, 59, 59, tzinfo=BEIJING_TZ)
    return build_license_key(customer_id="cache-co", expires_at=exp, secret=TEST_SECRET)


def test_warm_and_redis_hit(db_session, fake_redis):
    db_session.query(SystemSetting).filter(SystemSetting.setting_key == KEY_LICENSE_KEY).delete(
        synchronize_session=False
    )
    key = _valid_key()
    db_session.add(SystemSetting(setting_key=KEY_LICENSE_KEY, value=key))
    db_session.flush()

    status = warm_license_cache(db_session)
    assert status.valid is True
    raw = fake_redis.get(STATUS_KEY)
    assert raw
    cached = json.loads(raw)
    assert cached["valid"] is True
    assert cached["customer_id"] == "cache-co"

    hit = get_cached_status(db_session)
    assert hit.valid is True
    assert hit.customer_id == "cache-co"


def test_invalidate_forces_recompute(db_session, fake_redis, monkeypatch):
    db_session.query(SystemSetting).filter(SystemSetting.setting_key == KEY_LICENSE_KEY).delete(
        synchronize_session=False
    )
    key = _valid_key()
    db_session.add(SystemSetting(setting_key=KEY_LICENSE_KEY, value=key))
    db_session.flush()

    warm_license_cache(db_session)
    fake_redis.delete(STATUS_KEY)
    invalidate_license_cache()

    calls = {"n": 0}
    original = __import__("services.license_service", fromlist=["get_license_status"]).get_license_status

    def counting_get(db):
        calls["n"] += 1
        return original(db)

    monkeypatch.setattr("services.license_cache_service.get_license_status", counting_get)
    get_cached_status(db_session)
    assert calls["n"] >= 1


def test_redis_miss_uses_db(db_session, fake_redis):
    db_session.query(SystemSetting).filter(SystemSetting.setting_key == KEY_LICENSE_KEY).delete(
        synchronize_session=False
    )
    key = _valid_key()
    db_session.add(SystemSetting(setting_key=KEY_LICENSE_KEY, value=key))
    db_session.flush()

    assert fake_redis.get(STATUS_KEY) is None
    status = get_cached_status(db_session)
    assert status.valid is True
    assert fake_redis.get(STATUS_KEY) is not None
