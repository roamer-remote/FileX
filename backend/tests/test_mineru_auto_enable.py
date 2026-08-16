# Copyright (c) 2026 徐泽宇
"""032 PR-C: MinerU provider auto-enable at kb-extract startup."""

from __future__ import annotations

from unittest.mock import patch

from services.mineru_auto_enable_service import maybe_auto_enable_mineru_provider
from services.system_setting_service import KEY_KB_EXTRACT_PROVIDER, get_kb_extract_provider, update_settings


@patch("services.mineru_auto_enable_service.FILEX_ENABLE_MINERU_PROVIDER", False)
def test_auto_enable_skipped_when_env_off(db_session):
    assert maybe_auto_enable_mineru_provider(db_session) is False
    assert get_kb_extract_provider(db_session) == "legacy"


@patch("services.mineru_auto_enable_service.FILEX_ENABLE_MINERU_PROVIDER", True)
@patch("services.mineru_auto_enable_service._sidecar_healthy", return_value=True)
def test_auto_enable_legacy_to_mineru(_health, db_session):
    assert maybe_auto_enable_mineru_provider(db_session) is True
    assert get_kb_extract_provider(db_session) == "mineru"


@patch("services.mineru_auto_enable_service.FILEX_ENABLE_MINERU_PROVIDER", True)
@patch("services.mineru_auto_enable_service._sidecar_healthy", return_value=True)
def test_auto_enable_idempotent_when_already_mineru(_health, db_session):
    update_settings(db_session, {KEY_KB_EXTRACT_PROVIDER: "mineru"})
    db_session.commit()
    assert maybe_auto_enable_mineru_provider(db_session) is False
    assert get_kb_extract_provider(db_session) == "mineru"


@patch("services.mineru_auto_enable_service.FILEX_ENABLE_MINERU_PROVIDER", True)
@patch("services.mineru_auto_enable_service._sidecar_healthy", return_value=False)
def test_auto_enable_skipped_when_sidecar_unhealthy(_health, db_session):
    assert maybe_auto_enable_mineru_provider(db_session) is False
    assert get_kb_extract_provider(db_session) == "legacy"


@patch("services.mineru_auto_enable_service.FILEX_ENABLE_MINERU_PROVIDER", True)
@patch("services.mineru_auto_enable_service._sidecar_healthy", return_value=True)
def test_auto_enable_does_not_downgrade_docling(_health, db_session):
    update_settings(db_session, {KEY_KB_EXTRACT_PROVIDER: "docling"})
    db_session.commit()
    assert maybe_auto_enable_mineru_provider(db_session) is False
    assert get_kb_extract_provider(db_session) == "docling"
