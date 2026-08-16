# Copyright (c) 2026 徐泽宇
"""049 Phase B: SC-049B-001～005 acceptance tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import status
from sqlalchemy.exc import IntegrityError

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_enums import ExternalSyncDeletePolicy, ExternalSyncItemStatus
from models.kb_external_sync import KbExternalSyncItem, KbExternalSyncSource
from models.kb_extract_job import KbExtractJob
from models.kb_index_job import KbIndexJob
from models.operation_log import OperationLog
from services.kb_external_sync.notion_client import NotionClientError
from services.kb_external_sync.notion_runner import run_notion_sync
from services.kb_external_sync.types import ExternalPagePayload
from services.kb_external_sync.upsert_service import (
    finalize_upsert_index_jobs,
    notion_external_key,
    upsert_external_page,
)
from services.kb_index_service import run_index_job
from services.kb_search_service import search_kb
from services.md_hash_service import compute_md_content_hash
from services.sync_secret_service import encrypt_sync_secret
from services.workspace_service import ensure_personal_workspace


@pytest.fixture(autouse=True)
def _sync_secret_key(monkeypatch):
    monkeypatch.setenv("FILEX_SYNC_SECRET_KEY", "test-sync-secret-key-049")


def _vec(seed: float = 0.5) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = seed
    return v


def _make_source(db_session, user) -> KbExternalSyncSource:
    ws = ensure_personal_workspace(db_session, user)
    source = KbExternalSyncSource(
        workspace_id=ws.id,
        user_id=user.id,
        provider="notion",
        delete_policy=ExternalSyncDeletePolicy.keep_file.value,
        config_public_json={"database_id": "db-sc049b"},
        secret_ciphertext=encrypt_sync_secret("ntn_sc049b_token"),
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


def _run_index_jobs_for_file(db_session, file_id: int) -> None:
    jobs = (
        db_session.query(KbIndexJob)
        .filter(KbIndexJob.file_id == file_id)
        .order_by(KbIndexJob.id.asc())
        .all()
    )
    for job in jobs:
        if job.status in ("queued", "running"):
            run_index_job(db_session, job)


def test_sc_049b_001_first_sync_creates_file_and_unique_mapping(db_session, regular_user):
    """SC-049B-001: 首次 sync → 同 workspace 1 file + mapping；external_key 唯一。"""
    source = _make_source(db_session, regular_user)
    md = "# SC-049B-001\n\nFirst sync body\n"
    result = upsert_external_page(db_session, source, _payload("001", md))
    db_session.commit()

    assert result.created_file is True
    assert result.file_id is not None

    files_in_ws = (
        db_session.query(FileModel)
        .filter(FileModel.workspace_id == source.workspace_id, FileModel.user_id == source.user_id)
        .count()
    )
    assert files_in_ws == 1

    item = db_session.get(KbExternalSyncItem, result.item_id)
    assert item.external_key == notion_external_key("page-001")
    assert item.file_id == result.file_id
    assert item.sync_status == ExternalSyncItemStatus.active.value

    dup_count = (
        db_session.query(KbExternalSyncItem)
        .filter(
            KbExternalSyncItem.source_id == source.id,
            KbExternalSyncItem.external_key == item.external_key,
        )
        .count()
    )
    assert dup_count == 1


@patch("services.kb_search_service.embed_text")
@patch("services.kb_index_service._notify_file_index")
@patch("messaging.kb_index_publisher.publish_kb_index_job")
@patch("services.kb_embed_cache_service.embed_texts")
def test_sc_049b_002_resync_updates_hash_index_ready_and_searchable(
    mock_embed_texts,
    _mock_publish,
    _mock_notify,
    mock_embed_text,
    db_session,
    regular_user,
):
    """SC-049B-002: 源端改内容 → 同 file_id、md_content_hash 变、index ready、检索可见。"""
    mock_embed_texts.side_effect = lambda texts, **_kwargs: [_vec(0.8) for _ in texts]
    mock_embed_text.return_value = _vec(0.8)

    marker = "SC049B002UniquePhrase"
    source = _make_source(db_session, regular_user)
    md_v1 = f"# Doc\n\n{marker} alpha\n"
    md_v2 = f"# Doc\n\n{marker} beta\n"

    first = upsert_external_page(db_session, source, _payload("002", md_v1))
    db_session.commit()
    finalize_upsert_index_jobs(db_session, source, [first])
    _run_index_jobs_for_file(db_session, first.file_id)
    db_session.commit()

    f = db_session.get(FileModel, first.file_id)
    hash_v1 = f.md_content_hash
    assert hash_v1 == compute_md_content_hash(md_v1)
    assert f.index_status == "ready"

    second = upsert_external_page(db_session, source, _payload("002", md_v2))
    assert second.file_id == first.file_id
    assert second.created_file is False
    db_session.commit()
    finalize_upsert_index_jobs(db_session, source, [second])
    _run_index_jobs_for_file(db_session, second.file_id)
    db_session.commit()
    db_session.refresh(f)

    assert f.md_content_hash != hash_v1
    assert f.md_content_hash == compute_md_content_hash(md_v2)
    assert f.index_status == "ready"

    items, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        f"{marker} beta",
        file_ids=[f.id],
        top_k=5,
        hybrid=False,
    )
    assert items
    joined = " ".join(item.get("text", "") for item in items)
    assert "beta" in joined
    assert "alpha" not in joined


@patch("services.kb_external_sync.notion_runner.NotionClient")
def test_sc_049b_003_remote_delete_marks_deleted_remote_preserves_file(mock_client_cls, db_session, regular_user):
    """SC-049B-003: 源端删页 → deleted_remote、file_id 保留、deleted_at 非空、不再 enqueue。"""
    source = _make_source(db_session, regular_user)
    gone_key = notion_external_key("33333333-3333-3333-3333-333333333333")

    stale_item = KbExternalSyncItem(
        source_id=source.id,
        external_key=gone_key,
        sync_status=ExternalSyncItemStatus.active.value,
    )
    db_session.add(stale_item)
    db_session.flush()
    stale_file = FileModel(
        user_id=regular_user.id,
        workspace_id=source.workspace_id,
        filename="gone.md",
        original_name="gone.md",
        file_path="/tmp/gone-placeholder.md",
        file_size=1,
        mime_type="text/markdown",
        md5_hash="0" * 32,
        extract_status="not_needed",
        has_md=True,
    )
    db_session.add(stale_file)
    db_session.flush()
    stale_item.file_id = stale_file.id
    db_session.commit()

    before_jobs = db_session.query(KbIndexJob).filter(KbIndexJob.file_id == stale_file.id).count()

    client = mock_client_cls.return_value
    client.iter_database_pages.return_value = iter([])

    stats = run_notion_sync(db_session, source.id)
    assert stats.deleted_remote == 1

    db_session.refresh(stale_item)
    assert stale_item.sync_status == ExternalSyncItemStatus.deleted_remote.value
    assert stale_item.file_id == stale_file.id
    assert stale_item.deleted_at is not None
    assert db_session.get(FileModel, stale_file.id) is not None

    after_jobs = db_session.query(KbIndexJob).filter(KbIndexJob.file_id == stale_file.id).count()
    assert after_jobs == before_jobs
    assert (
        db_session.query(KbExtractJob).filter(KbExtractJob.file_id == stale_file.id).count() == 0
    )


@patch("services.kb_external_sync.notion_runner.NotionClient")
def test_sc_049b_004_secret_redaction_in_test_connection_and_audit(
    mock_client_cls, client, admin_jwt_token, db_session, admin_user
):
    """SC-049B-004: test-connection 错误与 operation_log 不含明文 token。"""
    ws = ensure_personal_workspace(db_session, admin_user)
    token = "ntn_sc049b_redact_secret_token_abcdefghij"
    create = client.post(
        "/api/admin/external-sync/sources",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json={
            "workspace_id": ws.id,
            "provider": "notion",
            "secret": token,
            "config_public_json": {"database_id": "db-redact"},
            "delete_policy": "keep_file",
            "is_active": True,
        },
    )
    assert create.status_code == status.HTTP_201_CREATED
    source_id = create.json()["id"]
    assert token not in create.text

    mock_client_cls.return_value.test_connection.side_effect = NotionClientError(
        f"401 Unauthorized Bearer {token}",
        status_code=401,
    )
    resp = client.post(
        f"/api/admin/external-sync/sources/{source_id}/test-connection",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert token not in resp.text

    log = (
        db_session.query(OperationLog)
        .filter(OperationLog.action == "测试外部同步连接", OperationLog.target_id == source_id)
        .order_by(OperationLog.id.desc())
        .first()
    )
    assert log is not None
    assert token not in (log.detail or "")


def test_sc_049b_005_duplicate_key_constraint_and_resync_single_file(db_session, regular_user):
    """SC-049B-005: DB 唯一约束 + 重复 sync 同 key 仅单 file。"""
    source = _make_source(db_session, regular_user)
    ext_key = notion_external_key("page-005")

    first = upsert_external_page(db_session, source, _payload("005", "# v1\n"))
    db_session.commit()
    second = upsert_external_page(db_session, source, _payload("005", "# v2\n"))
    db_session.commit()

    assert second.file_id == first.file_id
    mapping_rows = (
        db_session.query(KbExternalSyncItem)
        .filter(KbExternalSyncItem.source_id == source.id, KbExternalSyncItem.external_key == ext_key)
        .count()
    )
    assert mapping_rows == 1

    orphan_file = FileModel(
        user_id=regular_user.id,
        workspace_id=source.workspace_id,
        filename="orphan.md",
        original_name="orphan.md",
        file_path="/tmp/orphan.md",
        file_size=1,
        mime_type="text/markdown",
        md5_hash="1" * 32,
        extract_status="not_needed",
    )
    db_session.add(orphan_file)
    db_session.flush()

    duplicate = KbExternalSyncItem(
        source_id=source.id,
        external_key=ext_key,
        file_id=orphan_file.id,
        sync_status=ExternalSyncItemStatus.active.value,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
