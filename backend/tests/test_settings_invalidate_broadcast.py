# Copyright (c) 2026 徐泽宇
"""121: MQ fanout for cross-process system settings cache invalidation."""

from __future__ import annotations

from unittest.mock import patch

from models.system_setting import SystemSetting
from messaging.settings_invalidate_consumer import apply_settings_cache_invalidate
from services.system_setting_service import (
    KEY_KB_LARGE_DOC_CHAR_THRESHOLD,
    get_public_settings_dict,
    invalidate_all_settings_caches,
    update_settings,
)


def test_update_settings_publishes_cache_invalidate(db_session):
    with patch(
        "messaging.settings_invalidate_publisher.publish_settings_cache_invalidate"
    ) as publish:
        update_settings(db_session, {KEY_KB_LARGE_DOC_CHAR_THRESHOLD: "1000000"})
    publish.assert_called_once()


def test_invalidate_all_settings_caches_can_skip_broadcast(db_session):
    with patch(
        "messaging.settings_invalidate_publisher.publish_settings_cache_invalidate"
    ) as publish:
        invalidate_all_settings_caches(broadcast=False)
    publish.assert_not_called()


def test_apply_settings_cache_invalidate_reloads_from_db(db_session):
    update_settings(db_session, {KEY_KB_LARGE_DOC_CHAR_THRESHOLD: "400000"})
    _ = get_public_settings_dict(db_session)

    row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_LARGE_DOC_CHAR_THRESHOLD)
        .first()
    )
    assert row is not None
    row.value = "1000000"
    db_session.commit()

    assert get_public_settings_dict(db_session)[KEY_KB_LARGE_DOC_CHAR_THRESHOLD] == "400000"

    apply_settings_cache_invalidate()

    assert get_public_settings_dict(db_session)[KEY_KB_LARGE_DOC_CHAR_THRESHOLD] == "1000000"
