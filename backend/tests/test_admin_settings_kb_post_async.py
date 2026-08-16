# Copyright (c) 2026 徐泽宇
"""114: admin kb_post_async_enabled / kb_post_max_attempts settings."""

from __future__ import annotations

from models.system_setting import SystemSetting
from services.system_setting_service import (
    KEY_KB_POST_ASYNC_ENABLED,
    KEY_KB_POST_MAX_ATTEMPTS,
    get_public_settings_dict,
    invalidate_settings_cache,
    update_settings,
)


def test_update_settings_persists_kb_post_async_in_db_and_public_dict(db_session):
    update_settings(db_session, {KEY_KB_POST_ASYNC_ENABLED: "false"})
    invalidate_settings_cache()
    row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_POST_ASYNC_ENABLED)
        .first()
    )
    assert row is not None
    assert row.value == "false"
    d = get_public_settings_dict(db_session)
    assert d["kb_post_async_enabled"] == "false"


def test_admin_get_includes_kb_post_fields(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.get("/api/admin/system-settings", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "kb_post_async_enabled" in body
    assert "kb_post_max_attempts" in body
    assert isinstance(body["kb_post_async_enabled"], bool)
    assert isinstance(body["kb_post_max_attempts"], int)


def test_admin_put_kb_post_max_attempts(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r_put = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_post_max_attempts": 5},
    )
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["kb_post_max_attempts"] == 5

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["kb_post_max_attempts"] == 5
