# Copyright (c) 2026 徐泽宇
"""049 T-6: external sync upsert service."""

from datetime import datetime, timezone

import pytest

from models.kb_enums import ExternalSyncDeletePolicy, ExternalSyncItemStatus
from models.kb_external_sync import KbExternalSyncItem, KbExternalSyncSource
from models.kb_index_job import KbIndexJob
from models.kb_extract_job import KbExtractJob
from services.kb_external_sync.types import ExternalPagePayload
from services.kb_external_sync.upsert_service import (
    mark_item_deleted_remote,
    notion_external_key,
    upsert_external_page,
)
from services.md_hash_service import compute_md_content_hash
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
        config_public_json={"database_id": "db-test-001"},
        secret_ciphertext=encrypt_sync_secret("ntn_test_token"),
        is_active=True,
    )
    db_session.add(source)
    db_session.flush()
    return source


def _payload(key_suffix: str, body: str) -> ExternalPagePayload:
    return ExternalPagePayload(
        external_key=notion_external_key(f"page-{key_suffix}"),
        title=f"Page {key_suffix}",
        markdown=body,
        external_uri=f"https://notion.so/{key_suffix}",
        external_updated_at=datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc),
    )


def test_first_upsert_creates_file_and_mapping(db_session, regular_user):
    source = _make_source(db_session, regular_user)
    md = "# Hello\n\nWorld\n"
    result = upsert_external_page(db_session, source, _payload("a", md))
    db_session.commit()

    assert result.created_file is True
    assert result.content_changed is True
    assert result.index_job_id is not None

    item = db_session.get(KbExternalSyncItem, result.item_id)
    assert item.external_key == notion_external_key("page-a")
    assert item.file_id == result.file_id
    assert item.content_hash == compute_md_content_hash(md)

    from models.file import File as FileModel

    f = db_session.get(FileModel, result.file_id)
    assert f.workspace_id == source.workspace_id
    assert f.md5_hash == item.content_hash
    assert f.extract_status == "not_needed"
    assert f.has_md is True


def test_second_upsert_same_key_updates_same_file(db_session, regular_user):
    source = _make_source(db_session, regular_user)
    first = upsert_external_page(db_session, source, _payload("b", "# v1\n"))
    db_session.commit()
    second = upsert_external_page(db_session, source, _payload("b", "# v2\n"))
    db_session.commit()

    assert second.created_file is False
    assert second.file_id == first.file_id
    assert second.content_changed is True

    count = (
        db_session.query(KbExternalSyncItem)
        .filter(
            KbExternalSyncItem.source_id == source.id,
            KbExternalSyncItem.external_key == notion_external_key("page-b"),
        )
        .count()
    )
    assert count == 1


def test_unchanged_content_skips_index_job(db_session, regular_user):
    source = _make_source(db_session, regular_user)
    body = "# Same\n"
    upsert_external_page(db_session, source, _payload("c", body))
    db_session.commit()
    result = upsert_external_page(db_session, source, _payload("c", body))
    db_session.commit()
    assert result.content_changed is False
    assert result.index_job_id is None


def test_deleted_remote_does_not_enqueue(db_session, regular_user):
    source = _make_source(db_session, regular_user)
    result = upsert_external_page(db_session, source, _payload("d", "# gone\n"))
    db_session.commit()

    item = db_session.get(KbExternalSyncItem, result.item_id)
    before_jobs = db_session.query(KbIndexJob).filter(KbIndexJob.file_id == result.file_id).count()
    mark_item_deleted_remote(db_session, item)
    db_session.commit()
    after_jobs = db_session.query(KbIndexJob).filter(KbIndexJob.file_id == result.file_id).count()
    assert item.sync_status == ExternalSyncItemStatus.deleted_remote.value
    assert item.deleted_at is not None
    assert item.file_id == result.file_id
    assert after_jobs == before_jobs
    assert db_session.query(KbExtractJob).filter(KbExtractJob.file_id == result.file_id).count() == 0
