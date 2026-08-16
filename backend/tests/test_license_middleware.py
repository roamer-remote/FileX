# Copyright (c) 2026 徐泽宇
"""LicenseMiddleware allowlist 与 403 响应（021）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from datetime import datetime, timedelta

import pytest
from fastapi import status

from models.system_setting import SystemSetting
from services.license_service import (
    KEY_LICENSE_KEY,
    KEY_LICENSE_TRIAL_STARTED_AT,
    LICENSE_TRIAL_DAYS,
    REASON_TRIAL_EXPIRED,
    build_license_key,
    get_license_status,
)
from utils.timezone import BEIJING_TZ

TEST_SECRET = "middleware-test-hmac-secret"


@pytest.fixture(autouse=True)
def _license_mw_env(monkeypatch, db_session):
    monkeypatch.setenv("FILEX_LICENSE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.delenv("FILEX_ENV", raising=False)
    monkeypatch.setattr("services.license_service.license_hmac_secret", lambda: TEST_SECRET)
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


def _expired_trial(db_session, monkeypatch):
    started = datetime(2020, 1, 1, tzinfo=BEIJING_TZ)
    db_session.add(SystemSetting(setting_key=KEY_LICENSE_TRIAL_STARTED_AT, value=started.isoformat()))
    db_session.flush()
    after = started + timedelta(days=LICENSE_TRIAL_DAYS + 1)
    monkeypatch.setattr("services.license_service.beijing_now", lambda: after)


class TestLicenseMiddlewareAllowlist:
    """授权中间件allowlist 单元测试。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-10
    """
    def test_health_ok_when_expired(self, client, db_session, monkeypatch):
        _expired_trial(db_session, monkeypatch)
        r = client.get("/api/health")
        assert r.status_code == status.HTTP_200_OK

    def test_meta_runtime_ok_when_expired(self, client, db_session, monkeypatch):
        _expired_trial(db_session, monkeypatch)
        r = client.get("/api/meta/runtime")
        assert r.status_code == status.HTTP_200_OK

    def test_license_status_ok_when_expired(self, client, db_session, monkeypatch):
        _expired_trial(db_session, monkeypatch)
        r = client.get("/api/license/status")
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["valid"] is False


class TestLicenseMiddlewareBlock:
    """授权中间件block 单元测试。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-10
    """
    def test_files_403_when_expired(self, client, db_session, monkeypatch, jwt_token):
        _expired_trial(db_session, monkeypatch)
        r = client.get("/api/files", headers={"Authorization": f"Bearer {jwt_token}"})
        assert r.status_code == status.HTTP_403_FORBIDDEN
        body = r.json()
        assert body["code"] == "license_expired"
        assert body.get("expires_at")
        assert "授权" in body["detail"]

    def test_login_403_when_expired(self, client, db_session, monkeypatch, admin_user):
        _expired_trial(db_session, monkeypatch)
        r = client.post(
            "/api/auth/login",
            json={"username": "adminuser", "password": "password123"},
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert r.json()["code"] == "license_expired"

    def test_invalid_key_code(self, client, db_session, monkeypatch, jwt_token):
        db_session.add(SystemSetting(setting_key=KEY_LICENSE_KEY, value="FILEX1.notvalid.sig"))
        db_session.flush()
        r = client.get("/api/files", headers={"Authorization": f"Bearer {jwt_token}"})
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert r.json()["code"] == "license_invalid"

    def test_share_download_403_when_expired(self, client, db_session, monkeypatch):
        """SC-006：过期时分享下载亦被 Middleware 阻断。"""
        _expired_trial(db_session, monkeypatch)
        r = client.get("/api/share/any-token/download")
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert r.json()["code"] == "license_expired"


class TestLicenseMiddlewarePass:
    """授权中间件pass 单元测试。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇
    """
    def test_files_ok_with_valid_key(self, client, db_session, jwt_token):
        exp = datetime(2030, 12, 31, 23, 59, 59, tzinfo=BEIJING_TZ)
        key = build_license_key(customer_id="mw", expires_at=exp, secret=TEST_SECRET)
        db_session.add(SystemSetting(setting_key=KEY_LICENSE_KEY, value=key))
        db_session.flush()
        r = client.get("/api/files", headers={"Authorization": f"Bearer {jwt_token}"})
        assert r.status_code == status.HTTP_200_OK
