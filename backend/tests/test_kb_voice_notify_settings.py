# Copyright (c) 2026 徐泽宇
"""035: kb_voice_notify_enabled 系统参数。"""


def test_client_settings_kb_voice_notify_default_true(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    r = client.get("/api/settings/clipboard", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["kb_voice_notify_enabled"] is True


def test_admin_put_kb_voice_notify_toggle(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    r_off = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_voice_notify_enabled": False},
    )
    assert r_off.status_code == 200, r_off.text
    assert r_off.json()["kb_voice_notify_enabled"] is False

    r_client = client.get("/api/settings/clipboard", headers=headers)
    assert r_client.status_code == 200, r_client.text
    assert r_client.json()["kb_voice_notify_enabled"] is False

    r_on = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_voice_notify_enabled": True},
    )
    assert r_on.status_code == 200, r_on.text
    assert r_on.json()["kb_voice_notify_enabled"] is True


# 153: voice playback TTL — admin default, save, echo, and invalid values
def test_kb_voice_playback_ttl_default_and_update(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    r = client.get("/api/admin/system-settings", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["kb_voice_notify_playback_ttl_seconds"] == 120

    r_put = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_voice_notify_playback_ttl_seconds": 30},
    )
    assert r_put.status_code == 200, r_put.text
    assert r_put.json()["kb_voice_notify_playback_ttl_seconds"] == 30

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["kb_voice_notify_playback_ttl_seconds"] == 30


def test_kb_voice_playback_ttl_client_settings(client, jwt_token):
    headers = {"Authorization": f"Bearer {jwt_token}"}

    r = client.get("/api/settings/clipboard", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["kb_voice_notify_playback_ttl_seconds"] == 120


def test_kb_voice_playback_ttl_rejects_out_of_range(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    for value in (0, 3601):
        r = client.put(
            "/api/admin/system-settings",
            headers=headers,
            json={"kb_voice_notify_playback_ttl_seconds": value},
        )
        assert r.status_code == 422, r.text
        body = r.json()
        # confirm the field name appears in the validation error payload
        joined = repr(body)
        assert "kb_voice_notify_playback_ttl_seconds" in joined
