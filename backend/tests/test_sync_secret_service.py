# Copyright (c) 2026 徐泽宇
"""049 Phase B: sync_secret_service + external sync schema."""

import pytest
from sqlalchemy.exc import IntegrityError

from models.kb_enums import ExternalSyncDeletePolicy, ExternalSyncItemStatus
from models.kb_external_sync import KbExternalSyncItem, KbExternalSyncSource
from services.sync_secret_service import (
    SyncSecretNotConfiguredError,
    decrypt_sync_secret,
    encrypt_sync_secret,
    redact_sync_secret,
    require_sync_secret_configured,
    sync_secret_configured,
    sync_secret_preview,
)


@pytest.fixture(autouse=True)
def _sync_secret_key(monkeypatch):
    monkeypatch.setenv("FILEX_SYNC_SECRET_KEY", "test-sync-secret-key-049")


def test_encrypt_decrypt_roundtrip():
    plain = "secret_notion_integration_token_abc123"
    blob = encrypt_sync_secret(plain)
    assert len(blob) >= 12 + 16
    assert decrypt_sync_secret(blob) == plain


def test_decrypt_wrong_key_fails(monkeypatch):
    blob = encrypt_sync_secret("token-one")
    monkeypatch.setenv("FILEX_SYNC_SECRET_KEY", "different-key")
    with pytest.raises(ValueError, match="cannot decrypt"):
        decrypt_sync_secret(blob)


def test_sync_secret_preview():
    assert sync_secret_preview("") == ""
    assert sync_secret_preview("short") == "****"
    assert sync_secret_preview("123456789012") == "9012"


def test_redact_sync_secret():
    token = "ntn_secret_abcdefghijklmnop"
    msg = f"Notion error: Authorization Bearer {token} failed"
    assert token not in redact_sync_secret(msg, token)
    assert "****" in redact_sync_secret(msg, token)
    assert redact_sync_secret("safe message", token) == "safe message"


def test_require_sync_secret_configured_in_production(monkeypatch):
    monkeypatch.delenv("FILEX_ENV", raising=False)
    monkeypatch.delenv("FILEX_SYNC_SECRET_KEY", raising=False)
    assert not sync_secret_configured()
    with pytest.raises(SyncSecretNotConfiguredError):
        require_sync_secret_configured()


def test_sync_secret_dev_default_when_development(monkeypatch):
    monkeypatch.setenv("FILEX_ENV", "development")
    monkeypatch.delenv("FILEX_SYNC_SECRET_KEY", raising=False)
    assert sync_secret_configured()
    blob = encrypt_sync_secret("dev-token")
    assert decrypt_sync_secret(blob) == "dev-token"


@pytest.mark.filterwarnings(
    "ignore:transaction already deassociated from connection:sqlalchemy.exc.SAWarning"
)
def test_external_sync_item_unique_constraint(db_session, regular_user):
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)

    source = KbExternalSyncSource(
        workspace_id=ws.id,
        user_id=regular_user.id,
        provider="notion",
        delete_policy=ExternalSyncDeletePolicy.keep_file.value,
        config_public_json={"space_id": "test"},
    )
    db_session.add(source)
    db_session.flush()

    item = KbExternalSyncItem(
        source_id=source.id,
        external_key="notion:page:abc",
        sync_status=ExternalSyncItemStatus.active.value,
    )
    db_session.add(item)
    db_session.commit()

    dup = KbExternalSyncItem(
        source_id=source.id,
        external_key="notion:page:abc",
        sync_status=ExternalSyncItemStatus.active.value,
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
