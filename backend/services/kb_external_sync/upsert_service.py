# Copyright (c) 2026 徐泽宇
"""External page upsert: mapping row + md sidecar + index enqueue (049 T-6)."""

from __future__ import annotations

import os
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import UPLOAD_DIR
from models.file import File as FileModel
from models.kb_enums import ExternalSyncItemStatus
from models.kb_external_sync import KbExternalSyncItem, KbExternalSyncSource
from services.file_service import get_mime_type
from services.kb_external_sync.types import ExternalPagePayload, UpsertExternalPageResult
from services.kb_extract_service import STATUS_NOT_NEEDED
from services.md_hash_service import compute_md_content_hash
from services.md_note_service import save_md_note_for_file


def notion_external_key(page_id: str) -> str:
    pid = (page_id or "").strip().replace("-", "")
    return f"notion:page:{pid}"


def _advisory_lock_external_key(db: Session, source_id: int, external_key: str) -> None:
    digest = zlib.crc32(f"{source_id}:{external_key}".encode("utf-8")) & 0x7FFFFFFF
    db.execute(
        text("SELECT pg_advisory_xact_lock(CAST(:ns AS integer), CAST(:key AS integer))"),
        {"ns": 49, "key": digest},
    )


def _sanitize_sync_title(title: str, *, fallback: str) -> str:
    base = (title or "").strip() or fallback
    base = base.replace("/", "-").replace("\\", "-")[:200]
    if not base.lower().endswith(".md"):
        base = f"{base}.md"
    return base


def _placeholder_sync_path(user_id: int, name: str) -> str:
    uid = uuid.uuid4().hex[:12]
    rel = Path(str(user_id)) / "external-sync" / f"{uid}_{name}"
    full = Path(UPLOAD_DIR) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    if not full.exists():
        full.write_bytes(b"")
    return str(full)


def _create_external_sync_file(
    db: Session,
    source: KbExternalSyncSource,
    *,
    title: str,
    markdown: str,
    content_hash: str,
) -> FileModel:
    safe_name = _sanitize_sync_title(title, fallback=content_hash[:8])
    encoded = markdown.encode("utf-8")
    path = _placeholder_sync_path(source.user_id, safe_name)
    f = FileModel(
        user_id=source.user_id,
        workspace_id=source.workspace_id,
        filename=os.path.basename(path),
        original_name=safe_name,
        file_path=path,
        file_size=len(encoded),
        mime_type=get_mime_type(safe_name) or "text/markdown",
        md5_hash=content_hash,
        has_md=False,
        index_status="pending",
        extract_status=STATUS_NOT_NEEDED,
        page_kind="source",
    )
    db.add(f)
    db.flush()
    return f


def mark_item_deleted_remote(
    db: Session,
    item: KbExternalSyncItem,
    *,
    detected_at: datetime | None = None,
) -> bool:
    if item.sync_status == ExternalSyncItemStatus.deleted_remote.value:
        return False
    when = detected_at or datetime.now(timezone.utc)
    item.sync_status = ExternalSyncItemStatus.deleted_remote.value
    item.deleted_at = when
    return True


def upsert_external_page(
    db: Session,
    source: KbExternalSyncSource,
    payload: ExternalPagePayload,
) -> UpsertExternalPageResult:
    """Upsert one external page into files + kb_external_sync_items.

    Uses advisory lock + INSERT-on-conflict retry for concurrent first sync.
    Does not commit; caller publishes index jobs after commit.
    """
    content_hash = compute_md_content_hash(payload.markdown)
    _advisory_lock_external_key(db, source.id, payload.external_key)

    item = (
        db.query(KbExternalSyncItem)
        .filter(
            KbExternalSyncItem.source_id == source.id,
            KbExternalSyncItem.external_key == payload.external_key,
        )
        .first()
    )
    created_file = False

    if item is None:
        file = _create_external_sync_file(
            db,
            source,
            title=payload.title,
            markdown=payload.markdown,
            content_hash=content_hash,
        )
        item = KbExternalSyncItem(
            source_id=source.id,
            external_key=payload.external_key,
            file_id=file.id,
            external_uri=payload.external_uri,
            external_updated_at=payload.external_updated_at,
            content_hash=content_hash,
            sync_status=ExternalSyncItemStatus.active.value,
            deleted_at=None,
        )
        db.add(item)
        sp = db.begin_nested()
        try:
            db.flush()
            created_file = True
        except IntegrityError:
            sp.rollback()
            db.expunge(item)
            orphan_id = file.id
            item = (
                db.query(KbExternalSyncItem)
                .filter(
                    KbExternalSyncItem.source_id == source.id,
                    KbExternalSyncItem.external_key == payload.external_key,
                )
                .with_for_update()
                .one()
            )
            file = db.get(FileModel, item.file_id)
            if file is None:
                raise RuntimeError("external sync item missing file_id")
            orphan = db.get(FileModel, orphan_id)
            if orphan is not None and orphan.id != file.id:
                db.delete(orphan)
                db.flush()
            created_file = False
    else:
        if item.file_id is None:
            file = _create_external_sync_file(
                db,
                source,
                title=payload.title,
                markdown=payload.markdown,
                content_hash=content_hash,
            )
            item.file_id = file.id
            created_file = True
        else:
            file = db.get(FileModel, item.file_id)
            if file is None:
                raise RuntimeError(f"sync item {item.id} references missing file")

    if item.sync_status == ExternalSyncItemStatus.deleted_remote.value:
        item.sync_status = ExternalSyncItemStatus.active.value
        item.deleted_at = None

    if payload.title and file.original_name != _sanitize_sync_title(payload.title, fallback=file.original_name):
        file.original_name = _sanitize_sync_title(payload.title, fallback=file.original_name)

    file.md5_hash = content_hash
    item.external_uri = payload.external_uri
    item.external_updated_at = payload.external_updated_at
    item.content_hash = content_hash
    item.sync_status = ExternalSyncItemStatus.active.value
    item.deleted_at = None

    job_id = save_md_note_for_file(
        db,
        source.user_id,
        file,
        payload.markdown,
        enqueue_vector_index=True,
    )
    content_changed = job_id is not None

    return UpsertExternalPageResult(
        file_id=file.id,
        item_id=item.id,
        created_file=created_file,
        content_changed=content_changed,
        index_job_id=job_id,
    )


def finalize_upsert_index_jobs(
    db: Session,
    source: KbExternalSyncSource,
    results: list[UpsertExternalPageResult],
) -> None:
    from services.md_note_service import publish_md_note_index_job, sync_kb_index_after_md_note

    for res in results:
        if res.index_job_id is not None:
            publish_md_note_index_job(db, source.user_id, res.file_id, res.index_job_id)
    sync_kb_index_after_md_note(db, source.user_id)
