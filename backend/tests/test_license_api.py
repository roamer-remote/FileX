# Copyright (c) 2026 徐泽宇
"""License API 与 api-key-status 集成（021）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from datetime import datetime, timedelta

import pytest
from fastapi import status

from models.system_setting import SystemSetting
from routers import license as license_router
from services.license_service import (
    KEY_LICENSE_KEY,
    KEY_LICENSE_TRIAL_STARTED_AT,
    LICENSE_TRIAL_DAYS,
    build_license_key,
    get_license_status,
)
from utils.timezone import BEIJING_TZ

TEST_SECRET = "api-test-hmac-secret"


@pytest.fixture(autouse=True)
def _license_api_env(monkeypatch, db_session):
    monkeypatch.setenv("FILEX_LICENSE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.delenv("FILEX_ENV", raising=False)
    monkeypatch.setattr("services.license_service.license_hmac_secret", lambda: TEST_SECRET)
    license_router.reset_activate_rate_limit_for_tests()
    db_session.query(SystemSetting).filter(
        SystemSetting.setting_key.in_([KEY_LICENSE_KEY, KEY_LICENSE_TRIAL_STARTED_AT])
    ).delete(synchronize_session=False)
    db_session.flush()

    def _cached(_db):
        return get_license_status(db_session)

    monkeypatch.setattr("services.license_cache_service.get_cached_status", _cached)
    monkeypatch.setattr("middleware.license.get_cached_status", _cached)
    monkeypatch.setattr("routers.license.get_cached_status", _cached)
    from services import license_cache_service as lc

    lc.invalidate_license_cache()
    yield
    lc.invalidate_license_cache()
    license_router.reset_activate_rate_limit_for_tests()


def _future_key(customer: str = "api-co") -> str:
    exp = datetime(2030, 6, 1, 23, 59, 59, tzinfo=BEIJING_TZ)
    return build_license_key(customer_id=customer, expires_at=exp, secret=TEST_SECRET)


def _set_expired_trial(db_session, monkeypatch):
    started = datetime(2025, 1, 1, tzinfo=BEIJING_TZ)
    db_session.add(SystemSetting(setting_key=KEY_LICENSE_TRIAL_STARTED_AT, value=started.isoformat()))
    db_session.flush()
    monkeypatch.setattr(
        "services.license_service.beijing_now",
        lambda: started + timedelta(days=LICENSE_TRIAL_DAYS + 1),
    )


class TestLicenseStatusApi:
    """授权状态API 单元测试。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-10
    """
    def test_status_trial_valid(self, client):
        r = client.get("/api/license/status")
        assert r.status_code == status.HTTP_200_OK
        d = r.json()
        assert d["valid"] is True
        assert d["in_trial"] is True

    def test_status_with_key_masked(self, client, db_session):
        key = _future_key()
        db_session.add(SystemSetting(setting_key=KEY_LICENSE_KEY, value=key))
        db_session.flush()
        r = client.get("/api/license/status")
        d = r.json()
        assert d["valid"] is True
        assert d["license_key_masked"] == f"****{key[-4:]}"
        assert key not in str(d)


class TestLicenseActivateApi:
    """授权激活API 单元测试。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-10
    """
    def test_activate_success(self, client, db_session, admin_user):
        key = _future_key("activated")
        r = client.post(
            "/api/license/activate",
            json={
                "license_key": key,
                "admin_username": "adminuser",
                "admin_password": "password123",
            },
        )
        assert r.status_code == status.HTTP_200_OK
        d = r.json()
        assert d["valid"] is True
        assert d["customer_id"] == "activated"
        row = db_session.query(SystemSetting).filter(SystemSetting.setting_key == KEY_LICENSE_KEY).one()
        assert row.value == key

    def test_activate_bad_admin(self, client, admin_user):
        r = client.post(
            "/api/license/activate",
            json={
                "license_key": _future_key(),
                "admin_username": "adminuser",
                "admin_password": "wrong",
            },
        )
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_activate_non_admin(self, client, regular_user):
        r = client.post(
            "/api/license/activate",
            json={
                "license_key": _future_key(),
                "admin_username": "testuser",
                "admin_password": "password123",
            },
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_activate_rate_limit(self, client, admin_user, monkeypatch):
        calls = {"n": 0}
        real = license_router._check_activate_rate_limit

        def counting(ip):
            calls["n"] += 1
            return real(ip)

        monkeypatch.setattr(license_router, "_check_activate_rate_limit", counting)
        body = {
            "license_key": "FILEX1.bad",
            "admin_username": "adminuser",
            "admin_password": "password123",
        }
        for _ in range(5):
            client.post("/api/license/activate", json=body)
        r = client.post("/api/license/activate", json=body)
        assert r.status_code == status.HTTP_429_TOO_MANY_REQUESTS


class TestAdminLicenseApi:
    """管理授权API 单元测试。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-10
    """
    def test_admin_get(self, client, admin_jwt_token, db_session):
        key = _future_key("admin-view")
        db_session.add(SystemSetting(setting_key=KEY_LICENSE_KEY, value=key))
        db_session.flush()
        r = client.get(
            "/api/admin/license",
            headers={"Authorization": f"Bearer {admin_jwt_token}"},
        )
        assert r.status_code == status.HTTP_200_OK
        d = r.json()
        assert d["customer_id"] == "admin-view"
        assert d["license_hmac_secret"] == TEST_SECRET
        assert d["license_hmac_secret_effective"] == TEST_SECRET

    def test_public_status_hides_hmac_secret(self, client):
        r = client.get("/api/license/status")
        assert r.status_code == status.HTTP_200_OK
        assert "license_hmac_secret" not in r.json()
        assert "license_hmac_secret_effective" not in r.json()

    def test_admin_put(self, client, admin_jwt_token, db_session):
        key = _future_key("admin-put")
        r = client.put(
            "/api/admin/license",
            headers={"Authorization": f"Bearer {admin_jwt_token}"},
            json={"license_key": key},
        )
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["customer_id"] == "admin-put"


class TestApiKeyStatusLicense:
    """API密钥状态授权 单元测试。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-10
    """
    def test_expired_license_probe(self, client, db_session, monkeypatch, active_api_key):
        _set_expired_trial(db_session, monkeypatch)
        r = client.get(
            "/api/external/api-key-status",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        )
        assert r.status_code == status.HTTP_200_OK
        d = r.json()
        assert d["valid"] is False
        assert d["reason"] == "license_expired"
        assert d.get("hint")
