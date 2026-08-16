# Copyright (c) 2026 徐泽宇
"""078 P3: read-only list/get SAG events for KB chunk panel."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models.kb_event import KbEvent
from models.kb_event_entity import KbEventEntity
from models.kb_chunk import KbChunk
from models.user import User
from services.acl_service import get_readable_file

SAG_EVENTS_PAGE_SIZE_MAX = 100


def _event_to_dict(event: KbEvent, entities: list[KbEventEntity]) -> dict[str, Any]:
    return {
        "id": int(event.id),
        "chunk_id": int(event.chunk_id),
        "chunk_index": None,
        "title": event.title,
        "summary": event.summary or "",
        "content": event.content,
        "extract_layer": event.extract_layer,
        "entities": [
            {
                "entity_name": row.entity_name,
                "entity_type": row.entity_type,
            }
            for row in entities
        ],
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def list_file_sag_events(
    db: Session,
    user: User,
    file_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(SAG_EVENTS_PAGE_SIZE_MAX, page_size))

    f = get_readable_file(db, user, file_id)
    if not f:
        return {"found": False}

    base = db.query(KbEvent).filter(KbEvent.file_id == file_id)
    total = base.count()
    events = (
        base.order_by(KbEvent.chunk_id.asc(), KbEvent.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    event_ids = [int(e.id) for e in events]
    entity_rows: list[KbEventEntity] = []
    if event_ids:
        entity_rows = (
            db.query(KbEventEntity)
            .filter(KbEventEntity.event_id.in_(event_ids))
            .order_by(KbEventEntity.entity_name.asc())
            .all()
        )
    by_event: dict[int, list[KbEventEntity]] = {}
    for row in entity_rows:
        by_event.setdefault(int(row.event_id), []).append(row)

    chunk_index_by_id: dict[int, int] = {}
    chunk_ids = [int(e.chunk_id) for e in events]
    if chunk_ids:
        for cid, cidx in db.query(KbChunk.id, KbChunk.chunk_index).filter(KbChunk.id.in_(chunk_ids)):
            chunk_index_by_id[int(cid)] = int(cidx)

    items = []
    for event in events:
        payload = _event_to_dict(event, by_event.get(int(event.id), []))
        payload["chunk_index"] = chunk_index_by_id.get(int(event.chunk_id))
        items.append(payload)

    return {
        "found": True,
        "file_id": file_id,
        "original_name": f.original_name,
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_chunk_sag_event(
    db: Session,
    user: User,
    file_id: int,
    chunk_id: int,
) -> dict[str, Any] | None:
    f = get_readable_file(db, user, file_id)
    if not f:
        return None

    event = (
        db.query(KbEvent)
        .filter(KbEvent.file_id == file_id, KbEvent.chunk_id == chunk_id)
        .first()
    )
    if not event:
        return None

    entities = (
        db.query(KbEventEntity)
        .filter(KbEventEntity.event_id == event.id)
        .order_by(KbEventEntity.entity_name.asc())
        .all()
    )
    payload = _event_to_dict(event, entities)
    chunk = db.query(KbChunk).filter(KbChunk.id == chunk_id, KbChunk.file_id == file_id).first()
    if chunk:
        payload["chunk_index"] = int(chunk.chunk_index)
    return payload
