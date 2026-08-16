# Copyright (c) 2026 徐泽宇
"""079：SAG 索引系统参数 admin / client API。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from services.system_setting_service import KEY_KB_SAG_EVENT_EXTRACT_ENABLED


def test_admin_get_sag_defaults(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.get("/api/admin/system-settings", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kb_sag_event_extract_enabled"] is False
    assert body["kb_sag_event_extract_mode"] == "rule"
    assert body["kb_sag_event_prompt_version"] == 1
    assert body["kb_sag_event_embed_enabled"] is False
    assert body["kb_sag_query_llm_enabled"] is False


def test_admin_put_sag_roundtrip(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    payload = {
        "kb_sag_event_extract_enabled": True,
        "kb_sag_event_extract_mode": "ollama",
        "kb_sag_event_prompt_version": 2,
        "kb_sag_event_embed_enabled": True,
        "kb_sag_query_llm_enabled": True,
    }
    r_put = client.put("/api/admin/system-settings", headers=headers, json=payload)
    assert r_put.status_code == 200, r_put.text
    body = r_put.json()
    assert body["kb_sag_event_extract_enabled"] is True
    assert body["kb_sag_event_extract_mode"] == "ollama"
    assert body["kb_sag_event_prompt_version"] == 2
    assert body["kb_sag_event_embed_enabled"] is True
    assert body["kb_sag_query_llm_enabled"] is True

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["kb_sag_event_extract_mode"] == "ollama"


def test_admin_put_invalid_sag_mode(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_sag_event_extract_mode": "invalid"},
    )
    assert r.status_code == 400, r.text


def test_admin_put_invalid_sag_prompt_version(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_sag_event_prompt_version": 0},
    )
    assert r.status_code == 400, r.text


def test_client_clipboard_sag_flag_default(client, jwt_token):
    r = client.get("/api/settings/clipboard", headers={"Authorization": f"Bearer {jwt_token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "kb_sag_event_extract_enabled" in body
    assert body["kb_sag_event_extract_enabled"] is False


def test_client_clipboard_sag_flag_follows_admin(client, admin_jwt_token, jwt_token, db_session):
    from services.system_setting_service import update_settings

    update_settings(db_session, {KEY_KB_SAG_EVENT_EXTRACT_ENABLED: "true"})
    r_admin = client.get("/api/settings/clipboard", headers={"Authorization": f"Bearer {admin_jwt_token}"})
    assert r_admin.status_code == 200, r_admin.text
    assert r_admin.json()["kb_sag_event_extract_enabled"] is True

    r_user = client.get("/api/settings/clipboard", headers={"Authorization": f"Bearer {jwt_token}"})
    assert r_user.status_code == 200, r_user.text
    assert r_user.json()["kb_sag_event_extract_enabled"] is True
