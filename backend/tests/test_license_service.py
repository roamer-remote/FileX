# Copyright (c) 2026 徐泽宇
"""Tests for license_service (021).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from datetime import datetime, timedelta

import pytest

from models.system_setting import SystemSetting
from services.license_service import (
    KEY_LICENSE_KEY,
    KEY_LICENSE_TRIAL_STARTED_AT,
    LICENSE_TRIAL_DAYS,
    LicenseError,
    REASON_EXPIRED,
    REASON_INVALID_SIGNATURE,
    REASON_MALFORMED,
    REASON_MISSING,
    REASON_TRIAL_EXPIRED,
    activate_license,
    assert_license_valid,
    build_license_key,
    get_license_status,
    parse_and_verify_license_key,
)
from utils.timezone import BEIJING_TZ

TEST_SECRET = "test-hmac-secret-for-license-pytest"


@pytest.fixture(autouse=True)
def _license_test_env(monkeypatch):
    monkeypatch.setenv("FILEX_LICENSE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.delenv("FILEX_ENV", raising=False)
    import importlib

    import config

    importlib.reload(config)


@pytest.fixture(autouse=True)
def _clear_license_rows(db_session):
    db_session.query(SystemSetting).filter(
        SystemSetting.setting_key.in_([KEY_LICENSE_KEY, KEY_LICENSE_TRIAL_STARTED_AT])
    ).delete(synchronize_session=False)
    db_session.flush()
    yield


def _future(days: int = 30) -> datetime:
    return datetime(2030, 6, 15, 23, 59, 59, tzinfo=BEIJING_TZ)


def _past(days_ago: int = 1) -> datetime:
    return datetime(2020, 1, 1, 23, 59, 59, tzinfo=BEIJING_TZ)


def test_build_and_verify_valid_key():
    key = build_license_key(customer_id="acme", expires_at=_future(), secret=TEST_SECRET)
    status = parse_and_verify_license_key(key)
    assert status.valid is True
    assert status.customer_id == "acme"
    assert status.in_trial is False
    assert status.reason is None


def test_expired_key(db_session):
    key = build_license_key(customer_id="old", expires_at=_past(), secret=TEST_SECRET)
    status = parse_and_verify_license_key(key)
    assert status.valid is False
    assert status.reason == REASON_EXPIRED


def test_wrong_signature():
    key = build_license_key(customer_id="x", expires_at=_future(), secret=TEST_SECRET)
    tampered = key[:-4] + "XXXX"
    status = parse_and_verify_license_key(tampered)
    assert status.valid is False
    assert status.reason == REASON_INVALID_SIGNATURE


def test_malformed_key():
    assert parse_and_verify_license_key("not-a-key").reason == REASON_MALFORMED
    assert parse_and_verify_license_key("").reason == REASON_MISSING


def test_trial_starts_and_valid(db_session, monkeypatch):
    fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=BEIJING_TZ)
    monkeypatch.setattr("services.license_service.beijing_now", lambda: fixed)

    status = get_license_status(db_session)
    assert status.valid is True
    assert status.in_trial is True
    assert status.days_remaining == LICENSE_TRIAL_DAYS

    row = db_session.query(SystemSetting).filter(SystemSetting.setting_key == KEY_LICENSE_TRIAL_STARTED_AT).one()
    assert row.value


def test_trial_expired(db_session, monkeypatch):
    started = datetime(2025, 1, 1, 0, 0, 0, tzinfo=BEIJING_TZ)
    db_session.add(SystemSetting(setting_key=KEY_LICENSE_TRIAL_STARTED_AT, value=started.isoformat()))
    db_session.flush()

    after_trial = started + timedelta(days=LICENSE_TRIAL_DAYS + 1)
    monkeypatch.setattr("services.license_service.beijing_now", lambda: after_trial)

    status = get_license_status(db_session)
    assert status.valid is False
    assert status.reason == REASON_TRIAL_EXPIRED


def test_dev_exempt(db_session, monkeypatch):
    monkeypatch.setenv("FILEX_ENV", "development")
    import importlib

    import config

    importlib.reload(config)
    monkeypatch.setattr("services.license_service.FILEX_ENV", "development")

    status = get_license_status(db_session)
    assert status.valid is True
    assert status.expires_at is None
    assert status.in_trial is False


def test_license_key_overrides_trial(db_session, monkeypatch):
    started = datetime(2026, 1, 1, 0, 0, 0, tzinfo=BEIJING_TZ)
    db_session.add(SystemSetting(setting_key=KEY_LICENSE_TRIAL_STARTED_AT, value=started.isoformat()))
    key = build_license_key(customer_id="paid", expires_at=_future(), secret=TEST_SECRET)
    db_session.add(SystemSetting(setting_key=KEY_LICENSE_KEY, value=key))
    db_session.flush()

    monkeypatch.setattr("services.license_service.beijing_now", lambda: started + timedelta(days=60))

    status = get_license_status(db_session)
    assert status.valid is True
    assert status.in_trial is False
    assert status.customer_id == "paid"


def test_activate_license(db_session):
    key = build_license_key(customer_id="corp", expires_at=_future(), secret=TEST_SECRET)
    status = activate_license(db_session, key, commit=False)
    assert status.valid is True
    assert status.customer_id == "corp"
    row = db_session.query(SystemSetting).filter(SystemSetting.setting_key == KEY_LICENSE_KEY).one()
    assert row.value == key


def test_activate_invalid_raises(db_session):
    with pytest.raises(ValueError, match="无效的 License Key"):
        activate_license(db_session, "FILEX1.bad.bad", commit=False)


def test_assert_license_valid_raises(db_session, monkeypatch):
    after = datetime(2025, 6, 1, tzinfo=BEIJING_TZ)
    db_session.add(
        SystemSetting(
            setting_key=KEY_LICENSE_TRIAL_STARTED_AT,
            value=datetime(2025, 1, 1, tzinfo=BEIJING_TZ).isoformat(),
        )
    )
    db_session.flush()
    monkeypatch.setattr("services.license_service.beijing_now", lambda: after)

    with pytest.raises(LicenseError) as exc:
        assert_license_valid(db_session)
    assert exc.value.status.reason == REASON_TRIAL_EXPIRED
