# Copyright (c) 2026 徐泽宇
"""049 T-6: Notion runner with mocked API."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from models.kb_enums import ExternalSyncDeletePolicy, ExternalSyncItemStatus
from models.kb_external_sync import KbExternalSyncItem, KbExternalSyncSource
from models.kb_index_job import KbIndexJob
from services.kb_external_sync.notion_runner import run_notion_sync
from services.kb_external_sync.upsert_service import notion_external_key
from services.sync_secret_service import encrypt_sync_secret
from services.workspace_service import ensure_personal_workspace


@pytest.fixture(autouse=True)
def _sync_secret_key(monkeypatch):
    monkeypatch.setenv("FILEX_SYNC_SECRET_KEY", "test-sync-secret-key-049")


def _make_source(db_session, user):
    ws = ensure_personal_workspace(db_session, user)
    source = KbExternalSyncSource(
        workspace_id=ws.id,
        user_id=user.id,
        provider="notion",
        delete_policy=ExternalSyncDeletePolicy.keep_file.value,
        config_public_json={"database_id": "db-abc"},
        secret_ciphertext=encrypt_sync_secret("ntn_test"),
        is_active=True,
    )
    db_session.add(source)
    db_session.commit()
    return source


@patch("services.kb_external_sync.notion_runner.NotionClient")
def test_run_notion_sync_upserts_and_marks_deleted(mock_client_cls, db_session, regular_user):
    source = _make_source(db_session, regular_user)

    page_live = {
        "id": "11111111-1111-1111-1111-111111111111",
        "url": "https://notion.so/live",
        "last_edited_time": "2026-06-20T10:00:00.000Z",
        "properties": {"Name": {"type": "title", "title": [{"plain_text": "Live"}]}},
    }
    page_gone_preexisting = notion_external_key("22222222-2222-2222-2222-222222222222")
    stale_item = KbExternalSyncItem(
        source_id=source.id,
        external_key=page_gone_preexisting,
        sync_status=ExternalSyncItemStatus.active.value,
    )
    db_session.add(stale_item)
    db_session.flush()
    from models.file import File as FileModel

    stale_file = FileModel(
        user_id=regular_user.id,
        workspace_id=source.workspace_id,
        filename="stale.md",
        original_name="stale.md",
        file_path="/tmp/stale-placeholder.md",
        file_size=1,
        mime_type="text/markdown",
        md5_hash="0" * 32,
        extract_status="not_needed",
    )
    db_session.add(stale_file)
    db_session.flush()
    stale_item.file_id = stale_file.id
    db_session.commit()

    client = MagicMock()
    client.iter_database_pages.return_value = iter([page_live])
    client.page_to_markdown.return_value = "# Live\n\nBody\n"
    mock_client_cls.return_value = client

    stats = run_notion_sync(db_session, source.id)

    assert stats.pages_seen == 1
    assert stats.upserted == 1
    assert stats.deleted_remote == 1

    live_key = notion_external_key(page_live["id"])
    live_item = (
        db_session.query(KbExternalSyncItem)
        .filter(KbExternalSyncItem.source_id == source.id, KbExternalSyncItem.external_key == live_key)
        .one()
    )
    assert live_item.sync_status == ExternalSyncItemStatus.active.value

    stale = (
        db_session.query(KbExternalSyncItem)
        .filter(KbExternalSyncItem.external_key == page_gone_preexisting)
        .one()
    )
    assert stale.sync_status == ExternalSyncItemStatus.deleted_remote.value
    assert stale.file_id == stale_file.id
    assert stale.deleted_at is not None

    jobs = db_session.query(KbIndexJob).filter(KbIndexJob.file_id == stale_file.id).count()
    assert jobs == 0
