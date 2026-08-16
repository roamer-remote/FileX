# Copyright (c) 2026 徐泽宇
"""113: admin RAPTOR master switch + large-doc raptor coupling."""

from __future__ import annotations

from models.system_setting import SystemSetting
from services.system_setting_service import (
    KEY_KB_LARGE_DOC_RAPTOR_ENABLED,
    KEY_KB_RAPTOR_ENABLED,
    KEY_KB_RAPTOR_MIN_CHARS,
    get_public_settings_dict,
    invalidate_settings_cache,
    update_settings,
)


def test_update_settings_persists_raptor_master_in_db_and_public_dict(db_session):
    update_settings(db_session, {KEY_KB_RAPTOR_ENABLED: "true"})
    invalidate_settings_cache()
    row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_RAPTOR_ENABLED)
        .first()
    )
    assert row is not None
    assert row.value == "true"
    d = get_public_settings_dict(db_session)
    assert d["kb_raptor_enabled"] == "true"


def test_master_off_forces_large_doc_raptor_off_when_patching_both(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_RAPTOR_ENABLED: "false",
            KEY_KB_LARGE_DOC_RAPTOR_ENABLED: "true",
        },
    )
    invalidate_settings_cache()
    d = get_public_settings_dict(db_session)
    assert d["kb_raptor_enabled"] == "false"
    assert d["kb_large_doc_raptor_enabled"] == "false"


def test_db_master_already_off_patch_large_only_forces_large_off(db_session):
    update_settings(db_session, {KEY_KB_RAPTOR_ENABLED: "false"})
    invalidate_settings_cache()
    update_settings(db_session, {KEY_KB_LARGE_DOC_RAPTOR_ENABLED: "true"})
    invalidate_settings_cache()
    d = get_public_settings_dict(db_session)
    assert d["kb_raptor_enabled"] == "false"
    assert d["kb_large_doc_raptor_enabled"] == "false"


def test_turning_master_off_clears_existing_large_doc_raptor(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_RAPTOR_ENABLED: "true",
            KEY_KB_LARGE_DOC_RAPTOR_ENABLED: "true",
        },
    )
    invalidate_settings_cache()
    update_settings(db_session, {KEY_KB_RAPTOR_ENABLED: "false"})
    invalidate_settings_cache()
    d = get_public_settings_dict(db_session)
    assert d["kb_raptor_enabled"] == "false"
    assert d["kb_large_doc_raptor_enabled"] == "false"


def test_normalize_invalid_raptor_min_chars_on_write(db_session):
    update_settings(db_session, {KEY_KB_RAPTOR_MIN_CHARS: "not-a-number"})
    invalidate_settings_cache()
    row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_RAPTOR_MIN_CHARS)
        .first()
    )
    assert row is not None
    assert row.value == "30000"


def test_admin_get_includes_raptor_fields(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r = client.get("/api/admin/system-settings", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "kb_raptor_enabled" in body
    assert "kb_raptor_min_chars" in body
    assert isinstance(body["kb_raptor_enabled"], bool)
    assert isinstance(body["kb_raptor_min_chars"], int)


def test_admin_put_master_off_forces_large_doc_raptor_off(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r_put = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={
            "kb_raptor_enabled": False,
            "kb_large_doc_raptor_enabled": True,
        },
    )
    assert r_put.status_code == 200, r_put.text
    body = r_put.json()
    assert body["kb_raptor_enabled"] is False
    assert body["kb_large_doc_raptor_enabled"] is False

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["kb_large_doc_raptor_enabled"] is False


def test_admin_put_large_only_when_master_already_off(client, admin_jwt_token):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}
    r_off = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_raptor_enabled": False},
    )
    assert r_off.status_code == 200, r_off.text
    assert r_off.json()["kb_raptor_enabled"] is False

    r_large = client.put(
        "/api/admin/system-settings",
        headers=headers,
        json={"kb_large_doc_raptor_enabled": True},
    )
    assert r_large.status_code == 200, r_large.text
    assert r_large.json()["kb_large_doc_raptor_enabled"] is False

    r_get = client.get("/api/admin/system-settings", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["kb_large_doc_raptor_enabled"] is False
