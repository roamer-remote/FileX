# Copyright (c) 2026 徐泽宇
"""MinerU settings DB persistence and runtime DB-first loading."""

from __future__ import annotations

from models.system_setting import SystemSetting
from services.mineru_config_service import get_mineru_runtime_config, invalidate_mineru_runtime_cache
from services.system_setting_service import (
    DEFAULTS,
    KEY_MINERU_RPC_TIMEOUT_SEC,
    MINERU_SETTING_KEYS,
    ensure_mineru_settings_defaults,
    get_public_settings_dict,
    invalidate_settings_cache,
    update_settings,
)


def test_ensure_mineru_settings_defaults_inserts_all_keys(db_session):
    db_session.query(SystemSetting).filter(
        SystemSetting.setting_key.in_(MINERU_SETTING_KEYS)
    ).delete(synchronize_session=False)
    db_session.commit()
    invalidate_settings_cache()
    invalidate_mineru_runtime_cache()

    assert ensure_mineru_settings_defaults(db_session) is True

    rows = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key.in_(MINERU_SETTING_KEYS))
        .all()
    )
    assert len(rows) == len(MINERU_SETTING_KEYS)
    by_key = {row.setting_key: row.value for row in rows}
    assert by_key[KEY_MINERU_RPC_TIMEOUT_SEC] == DEFAULTS[KEY_MINERU_RPC_TIMEOUT_SEC]


def test_get_mineru_runtime_config_uses_db_not_env(db_session, monkeypatch):
    monkeypatch.setenv("KB_EXTRACT_MINERU_TIMEOUT_SEC", "900")
    db_session.query(SystemSetting).filter(
        SystemSetting.setting_key.in_(MINERU_SETTING_KEYS)
    ).delete(synchronize_session=False)
    db_session.commit()
    invalidate_settings_cache()
    invalidate_mineru_runtime_cache()

    update_settings(db_session, {KEY_MINERU_RPC_TIMEOUT_SEC: "3600"})
    invalidate_mineru_runtime_cache()

    cfg = get_mineru_runtime_config(db_session, fresh=True)
    assert cfg.rpc_timeout_sec == 3600


def test_get_public_settings_dict_materializes_mineru_rows(db_session):
    db_session.query(SystemSetting).filter(
        SystemSetting.setting_key.in_(MINERU_SETTING_KEYS)
    ).delete(synchronize_session=False)
    db_session.commit()
    invalidate_settings_cache()

    settings = get_public_settings_dict(db_session)
    assert settings["mineru_rpc_timeout_sec"] == DEFAULTS[KEY_MINERU_RPC_TIMEOUT_SEC]

    count = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key.in_(MINERU_SETTING_KEYS))
        .count()
    )
    assert count == len(MINERU_SETTING_KEYS)
