# Copyright (c) 2026 徐泽宇
"""Insavlo provider configuration."""

import pytest

from models.system_setting import SystemSetting
from services.insavlo_config_service import (
    get_insavlo_runtime_config,
    is_insavlo_runtime_ready,
)
from services.system_setting_service import (
    KEY_KB_EXTRACT_INSAVLO_API_KEY,
    KEY_KB_EXTRACT_INSAVLO_BASE_URL,
    KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN,
    KEY_KB_EXTRACT_INSAVLO_ENABLED,
    KEY_KB_EXTRACT_INSAVLO_SKILL_CODE,
    KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
    KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET,
    get_public_settings_dict,
    invalidate_settings_cache,
    update_settings,
)
from utils.api_key_secret import encrypt_api_key_plaintext


def _configure_insavlo(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_EXTRACT_INSAVLO_ENABLED: "true",
            KEY_KB_EXTRACT_INSAVLO_BASE_URL: "https://demo.insavlo.com/insavlo/public-api/",
            KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN: "https://ding.yyyou.top/",
            KEY_KB_EXTRACT_INSAVLO_SKILL_CODE: "filex-md",
            KEY_KB_EXTRACT_INSAVLO_API_KEY: "insavlo-api-key",
            KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET: "insavlo-webhook-secret",
            KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES: "72",
        },
    )


def test_insavlo_runtime_ready_ignores_stale_settings_cache(db_session):
    _configure_insavlo(db_session)
    invalidate_settings_cache()
    get_public_settings_dict(db_session)

    import services.system_setting_service as system_setting_service

    with system_setting_service._cache_lock:
        assert system_setting_service._settings_cache is not None
        system_setting_service._settings_cache[KEY_KB_EXTRACT_INSAVLO_ENABLED] = "false"

    assert is_insavlo_runtime_ready(db_session) is True


def test_insavlo_runtime_ready_requires_complete_config(db_session):
    update_settings(db_session, {KEY_KB_EXTRACT_INSAVLO_ENABLED: "false"})
    assert is_insavlo_runtime_ready(db_session) is False

    _configure_insavlo(db_session)

    assert is_insavlo_runtime_ready(db_session) is True
    cfg = get_insavlo_runtime_config(db_session)
    assert cfg.base_url == "https://demo.insavlo.com/insavlo/public-api"
    assert cfg.callback_origin == "https://ding.yyyou.top"
    assert cfg.callback_url == "https://ding.yyyou.top/api/webhooks/insavlo/document-process"
    assert cfg.skill_code == "filex-md"
    assert cfg.api_key == "insavlo-api-key"
    assert cfg.webhook_secret == "insavlo-webhook-secret"
    assert cfg.timeout_minutes == 72


def test_insavlo_credentials_plaintext_in_db(db_session):
    _configure_insavlo(db_session)

    api_key_row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_EXTRACT_INSAVLO_API_KEY)
        .one()
    )
    secret_row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET)
        .one()
    )
    assert api_key_row.value == "insavlo-api-key"
    assert secret_row.value == "insavlo-webhook-secret"

    public = get_public_settings_dict(db_session)
    assert public["kb_extract_insavlo_api_key"] == "insavlo-api-key"
    assert public["kb_extract_insavlo_webhook_secret"] == "insavlo-webhook-secret"
    assert public["kb_extract_insavlo_has_api_key"] == "true"
    assert public["kb_extract_insavlo_has_webhook_secret"] == "true"
    assert public["kb_extract_insavlo_ready"] == "true"


def test_legacy_encrypted_insavlo_credentials_still_readable(db_session):
    encrypted_api_key = encrypt_api_key_plaintext("legacy-api-key")
    encrypted_webhook = encrypt_api_key_plaintext("legacy-webhook-secret")

    for key, value in (
        (KEY_KB_EXTRACT_INSAVLO_API_KEY, encrypted_api_key),
        (KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET, encrypted_webhook),
    ):
        row = (
            db_session.query(SystemSetting)
            .filter(SystemSetting.setting_key == key)
            .first()
        )
        if row is None:
            db_session.add(SystemSetting(setting_key=key, value=value))
        else:
            row.value = value
    db_session.commit()
    invalidate_settings_cache()

    public = get_public_settings_dict(db_session)
    assert public["kb_extract_insavlo_api_key"] == "legacy-api-key"
    assert public["kb_extract_insavlo_webhook_secret"] == "legacy-webhook-secret"


def test_insavlo_rejects_unsafe_base_url(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_EXTRACT_INSAVLO_ENABLED: "true",
            KEY_KB_EXTRACT_INSAVLO_BASE_URL: "http://127.0.0.1:8080",
        },
    )

    assert is_insavlo_runtime_ready(db_session) is False


def test_admin_test_insavlo_reports_format_only_success(client, admin_jwt_token, db_session):
    _configure_insavlo(db_session)

    r = client.post(
        "/api/admin/system-settings/test-insavlo",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["ready"] is True
    assert "首次提取任务" in data["message"]


def test_admin_get_insavlo_settings_returns_credentials(client, admin_jwt_token, db_session):
    _configure_insavlo(db_session)

    r = client.get(
        "/api/admin/system-settings",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["kb_extract_insavlo_api_key"] == "insavlo-api-key"
    assert data["kb_extract_insavlo_webhook_secret"] == "insavlo-webhook-secret"
    assert data["kb_extract_insavlo_has_api_key"] is True
    assert data["kb_extract_insavlo_has_webhook_secret"] is True


def test_admin_put_empty_insavlo_secret_keeps_existing_secret(client, admin_jwt_token, db_session):
    _configure_insavlo(db_session)

    r = client.put(
        "/api/admin/system-settings",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json={
            "kb_extract_insavlo_api_key": "",
            "kb_extract_insavlo_webhook_secret": "",
        },
    )

    assert r.status_code == 200, r.text
    cfg = get_insavlo_runtime_config(db_session)
    assert cfg.api_key == "insavlo-api-key"
    assert cfg.webhook_secret == "insavlo-webhook-secret"


def test_admin_can_clear_insavlo_secrets(client, admin_jwt_token, db_session):
    _configure_insavlo(db_session)

    r = client.put(
        "/api/admin/system-settings",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json={
            "clear_insavlo_api_key": True,
            "clear_insavlo_webhook_secret": True,
        },
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["kb_extract_insavlo_has_api_key"] is False
    assert data["kb_extract_insavlo_has_webhook_secret"] is False
    assert data["kb_extract_insavlo_api_key"] == ""
    assert data["kb_extract_insavlo_webhook_secret"] == ""
    assert data["kb_extract_insavlo_ready"] is False


def test_client_settings_include_only_insavlo_ready(client, jwt_token, db_session):
    _configure_insavlo(db_session)

    r = client.get(
        "/api/settings/clipboard",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["kb_extract_insavlo_ready"] is True
    assert "kb_extract_insavlo_api_key" not in data
    assert "kb_extract_insavlo_webhook_secret" not in data


def test_migrate_insavlo_timeout_hours_to_minutes(db_session):
    from models.system_setting import SystemSetting
    from services.system_setting_service import (
        KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS,
        KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
        migrate_insavlo_timeout_hours_to_minutes,
    )

    db_session.add(SystemSetting(setting_key=KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS, value="24"))
    db_session.commit()

    assert migrate_insavlo_timeout_hours_to_minutes(db_session) is True

    minutes_row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES)
        .one()
    )
    hours_row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS)
        .first()
    )
    assert minutes_row.value == "120"
    assert hours_row is None


@pytest.mark.parametrize(
    "hours,expected_minutes",
    [
        ("1", "60"),
        ("3", "120"),
        ("0", "2"),
    ],
)
def test_migrate_insavlo_timeout_hours_clamp(db_session, hours, expected_minutes):
    from models.system_setting import SystemSetting
    from services.system_setting_service import (
        KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS,
        KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
        migrate_insavlo_timeout_hours_to_minutes,
    )

    db_session.query(SystemSetting).filter(
        SystemSetting.setting_key.in_(
            [KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS, KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES]
        )
    ).delete(synchronize_session=False)
    db_session.add(SystemSetting(setting_key=KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS, value=hours))
    db_session.commit()

    assert migrate_insavlo_timeout_hours_to_minutes(db_session) is True

    minutes_row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES)
        .one()
    )
    assert minutes_row.value == expected_minutes


def test_migrate_insavlo_timeout_noop_when_no_legacy_key(db_session):
    from models.system_setting import SystemSetting
    from services.system_setting_service import (
        KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS,
        KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
        migrate_insavlo_timeout_hours_to_minutes,
    )

    db_session.query(SystemSetting).filter(
        SystemSetting.setting_key.in_(
            [KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS, KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES]
        )
    ).delete(synchronize_session=False)
    db_session.commit()

    assert migrate_insavlo_timeout_hours_to_minutes(db_session) is True
    assert (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES)
        .first()
        is None
    )


def test_migrate_insavlo_timeout_deletes_legacy_when_new_exists(db_session):
    from models.system_setting import SystemSetting
    from services.system_setting_service import (
        KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS,
        KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
        migrate_insavlo_timeout_hours_to_minutes,
    )

    db_session.query(SystemSetting).filter(
        SystemSetting.setting_key.in_(
            [KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS, KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES]
        )
    ).delete(synchronize_session=False)
    db_session.add(SystemSetting(setting_key=KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES, value="72"))
    db_session.add(SystemSetting(setting_key=KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS, value="24"))
    db_session.commit()

    assert migrate_insavlo_timeout_hours_to_minutes(db_session) is True

    minutes_row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES)
        .one()
    )
    hours_row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS)
        .first()
    )
    assert minutes_row.value == "72"
    assert hours_row is None


def test_load_settings_fallback_legacy_hours_before_migration(db_session):
    from models.system_setting import SystemSetting
    from services.system_setting_service import (
        KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS,
        KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
        get_fresh_public_settings_dict,
        invalidate_settings_cache,
    )

    db_session.query(SystemSetting).filter(
        SystemSetting.setting_key.in_(
            [KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS, KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES]
        )
    ).delete(synchronize_session=False)
    db_session.add(SystemSetting(setting_key=KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS, value="1"))
    db_session.commit()
    invalidate_settings_cache()

    settings = get_fresh_public_settings_dict(db_session)
    assert settings["kb_extract_insavlo_timeout_minutes"] == "60"
