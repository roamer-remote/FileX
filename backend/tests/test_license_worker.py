# Copyright (c) 2026 徐泽宇
"""Worker license gate (FR-501).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import pytest

from services.license_service import LICENSE_WORKER_SLEEP_SEC, require_license_or_wait


@pytest.fixture(autouse=True)
def _patch_license_cache(monkeypatch):
    monkeypatch.setattr("services.license_service.time.sleep", lambda _s: None)


def test_require_license_or_wait_valid(db_session, monkeypatch):
    monkeypatch.setattr(
        "services.license_cache_service.get_cached_status",
        lambda _db: type("S", (), {"valid": True, "reason": None})(),
    )
    assert require_license_or_wait(db_session) is True


def test_require_license_or_wait_invalid_sleeps(db_session, monkeypatch):
    slept = {"sec": None}

    def fake_sleep(sec):
        slept["sec"] = sec

    monkeypatch.setattr("services.license_service.time.sleep", fake_sleep)
    monkeypatch.setattr(
        "services.license_cache_service.get_cached_status",
        lambda _db: type("S", (), {"valid": False, "reason": "trial_expired"})(),
    )
    assert require_license_or_wait(db_session) is False
    assert slept["sec"] == LICENSE_WORKER_SLEEP_SEC
