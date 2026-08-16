# Copyright (c) 2026 徐泽宇
"""Notion database sync runner (049 T-6)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.kb_enums import ExternalSyncItemStatus
from models.kb_external_sync import KbExternalSyncItem, KbExternalSyncSource
from models.workspace import WORKSPACE_KIND_SHARED, Workspace
from services.kb_external_sync.notion_client import NotionClient, NotionClientError, page_title, parse_notion_datetime
from services.kb_external_sync.types import ExternalPagePayload, NotionSyncStats
from services.kb_external_sync.upsert_service import (
    finalize_upsert_index_jobs,
    mark_item_deleted_remote,
    notion_external_key,
    upsert_external_page,
)
from services.sync_secret_service import decrypt_sync_secret
from services.system_setting_service import is_shared_workspaces_enabled

logger = logging.getLogger(__name__)


class SourceNotRunnableError(RuntimeError):
    pass


def _database_id_from_config(source: KbExternalSyncSource) -> str:
    cfg = source.config_public_json or {}
    dbid = (cfg.get("database_id") or cfg.get("space_id") or "").strip()
    if not dbid:
        raise ValueError("config_public_json.database_id 未配置")
    return dbid


def ensure_source_runnable(db: Session, source: KbExternalSyncSource) -> None:
    if not source.is_active:
        raise SourceNotRunnableError("同步源未启用")
    if source.provider != "notion":
        raise SourceNotRunnableError(f"不支持的 provider: {source.provider}")
    ws = db.get(Workspace, source.workspace_id)
    if ws and ws.kind == WORKSPACE_KIND_SHARED and not is_shared_workspaces_enabled(db):
        raise SourceNotRunnableError("共享知识空间已关闭，跳过同步")


def run_notion_sync(db: Session, source_id: int) -> NotionSyncStats:
    source = db.get(KbExternalSyncSource, source_id)
    if source is None:
        raise ValueError("同步源不存在")
    ensure_source_runnable(db, source)
    if not source.secret_ciphertext:
        raise ValueError("同步源未配置凭据")

    token = decrypt_sync_secret(source.secret_ciphertext)
    database_id = _database_id_from_config(source)
    client = NotionClient(token)

    stats = NotionSyncStats()
    seen_keys: set[str] = set()
    pending_results: list = []

    for page in client.iter_database_pages(database_id):
        stats.pages_seen += 1
        page_id = page.get("id") or ""
        ext_key = notion_external_key(page_id)
        seen_keys.add(ext_key)
        markdown = client.page_to_markdown(page)
        payload = ExternalPagePayload(
            external_key=ext_key,
            title=page_title(page),
            markdown=markdown,
            external_uri=page.get("url"),
            external_updated_at=parse_notion_datetime(page.get("last_edited_time")),
        )
        result = upsert_external_page(db, source, payload)
        if result.content_changed:
            stats.upserted += 1
            if result.index_job_id is not None:
                stats.index_jobs += 1
                pending_results.append(result)
        else:
            stats.unchanged += 1
        db.flush()

    now = datetime.now(timezone.utc)
    active_items = (
        db.query(KbExternalSyncItem)
        .filter(
            KbExternalSyncItem.source_id == source.id,
            KbExternalSyncItem.sync_status == ExternalSyncItemStatus.active.value,
        )
        .all()
    )
    for item in active_items:
        if item.external_key not in seen_keys:
            if mark_item_deleted_remote(db, item, detected_at=now):
                stats.deleted_remote += 1

    source.last_sync_at = now
    db.commit()
    finalize_upsert_index_jobs(db, source, pending_results)
    return stats


def test_notion_connection(db: Session, source_id: int) -> dict:
    source = db.get(KbExternalSyncSource, source_id)
    if source is None:
        raise ValueError("同步源不存在")
    if not source.secret_ciphertext:
        raise ValueError("同步源未配置凭据")
    token = decrypt_sync_secret(source.secret_ciphertext)
    database_id = _database_id_from_config(source)
    client = NotionClient(token)
    meta = client.test_connection(database_id)
    return {"database_id": database_id, "title": meta.get("title")}
