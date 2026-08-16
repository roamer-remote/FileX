# Copyright (c) 2026 徐泽宇
"""GET /api/external/api-key-status — 前置探测，恒 200 JSON。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import pytest
from fastapi import status

from models.api_key import ApiKey


@pytest.fixture
def api_key_on_inactive_user(db_session, inactive_user):
    """属于已停用用户的有效上架密钥。"""
    from .conftest import _create_api_key

    return _create_api_key(db_session, inactive_user, is_active=True)


class TestApiKeyStatus:
    """API密钥状态 单元测试。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-11
    """
    def test_missing_authorization(self, client):
        r = client.get("/api/external/api-key-status")
        assert r.status_code == status.HTTP_200_OK
        d = r.json()
        assert d["valid"] is False
        assert d["reason"] == "missing_authorization"
        assert d.get("hint")
        assert d["username"] is None
        assert d["user_id"] is None

    def test_jwt_not_api_key(self, client, jwt_token):
        r = client.get(
            "/api/external/api-key-status",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert r.status_code == status.HTTP_200_OK
        d = r.json()
        assert d["valid"] is False
        assert d["reason"] == "not_api_key"
        assert d.get("hint")

    def test_invalid_api_key(self, client):
        r = client.get(
            "/api/external/api-key-status",
            headers={"Authorization": "Bearer fb_this_key_does_not_exist_in_db"},
        )
        assert r.status_code == status.HTTP_200_OK
        d = r.json()
        assert d["valid"] is False
        assert d["reason"] == "invalid_api_key"
        assert d.get("hint")
        assert d["username"] is None

    def test_valid(self, client, active_api_key):
        r = client.get(
            "/api/external/api-key-status",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        )
        assert r.status_code == status.HTTP_200_OK
        d = r.json()
        assert d["valid"] is True
        assert d["reason"] is None
        assert d.get("hint") in (None, "")
        assert d["username"] == "testuser"
        assert d["user_id"] == active_api_key.user_id


    def test_api_key_inactive(self, client, deactivated_api_key):
        r = client.get(
            "/api/external/api-key-status",
            headers={"Authorization": f"Bearer {deactivated_api_key._plaintext}"},
        )
        assert r.status_code == status.HTTP_200_OK
        d = r.json()
        assert d["valid"] is False
        assert d["reason"] == "api_key_inactive"
        assert d.get("hint")

    def test_user_inactive_includes_username(self, client, api_key_on_inactive_user):
        r = client.get(
            "/api/external/api-key-status",
            headers={"Authorization": f"Bearer {api_key_on_inactive_user._plaintext}"},
        )
        assert r.status_code == status.HTTP_200_OK
        d = r.json()
        assert d["valid"] is False
        assert d["reason"] == "user_inactive"
        assert d.get("hint")
        assert d["username"] == "inactiveuser"
        assert d["user_id"] is not None

    def test_probe_does_not_update_last_used(self, client, db_session, active_api_key):
        ak_id = active_api_key.id
        db_session.refresh(active_api_key)
        before = active_api_key.last_used_at

        for _ in range(2):
            r = client.get(
                "/api/external/api-key-status",
                headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
            )
            assert r.status_code == status.HTTP_200_OK
            assert r.json()["valid"] is True

        row = db_session.query(ApiKey).filter(ApiKey.id == ak_id).first()
        assert row.last_used_at == before

        r2 = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        )
        assert r2.status_code == status.HTTP_200_OK
        db_session.refresh(row)
        assert row.last_used_at is not None
        if before is not None:
            assert row.last_used_at != before
