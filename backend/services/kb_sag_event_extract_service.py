# Copyright (c) 2026 徐泽宇
"""077 P0: per-chunk SAG event + entity extraction (rule + optional Ollama JSON)."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_event import KbEvent
from models.kb_event_entity import KbEventEntity
from services.kb_entity_extract_service import _normalize_entity_name, extract_rule_entities
from schemas.llm_outputs import SagEventExtractionOutput
from services.kb_post_llm_service import chat_model
from services.system_setting_service import (
    get_kb_sag_event_extract_mode,
    is_kb_sag_event_extract_enabled,
)

logger = logging.getLogger(__name__)

_ENTITY_TYPES = frozenset({"person", "org", "metric", "concept", "location", "other"})
_MAX_LLM_CHARS = 8000
_SENTENCE_END_RE = re.compile(r"[。！？.!?]")


def delete_sag_events_for_file(db: Session, file_id: int) -> None:
    db.query(KbEvent).filter(KbEvent.file_id == file_id).delete()


def _first_sentence(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    match = _SENTENCE_END_RE.search(cleaned)
    if match:
        return cleaned[: match.end()].strip()
    return cleaned[:500]


def _rule_title(chunk: KbChunk, f: FileModel) -> str:
    heading = (chunk.heading_path or "").strip()
    if heading:
        parts = [part.strip() for part in heading.split("/") if part.strip()]
        if parts:
            return parts[-1][:512]
    first_line = (chunk.text or "").split("\n", 1)[0].strip()
    if first_line:
        return first_line[:512]
    return (f.original_name or "event")[:512]


def _heading_path_entities(chunk: KbChunk) -> list[dict[str, str]]:
    heading = (chunk.heading_path or "").strip()
    if not heading:
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for part in heading.split("/"):
        name = _normalize_entity_name(part.strip())
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({"entity_name": name, "entity_type": "concept"})
    return out


def _dedupe_entities(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in rows:
        name = row.get("entity_name") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        etype = str(row.get("entity_type") or "concept").lower()
        if etype not in _ENTITY_TYPES:
            etype = "other"
        out.append({"entity_name": name, "entity_type": etype})
    return out


def extract_rule_event_for_chunk(chunk: KbChunk, f: FileModel) -> tuple[dict[str, Any], list[dict[str, str]]]:
    title = _rule_title(chunk, f)
    content = chunk.text or title
    summary = _first_sentence(content) or title
    entities: list[dict[str, str]] = []
    for edge in extract_rule_entities([chunk]):
        entities.append(
            {
                "entity_name": edge["entity_name"],
                "entity_type": edge.get("entity_type") or "concept",
            }
        )
    entities.extend(_heading_path_entities(chunk))
    return (
        {
            "title": title,
            "summary": summary,
            "content": content,
            "extract_layer": "rule",
        },
        _dedupe_entities(entities),
    )


def _ollama_chat_json(
    db_or_prompt: Session | str, prompt: str | None = None
) -> SagEventExtractionOutput | None:
    if prompt is None:
        return chat_model(
            str(db_or_prompt), output_type=SagEventExtractionOutput,
            purpose="sag_event_extract", fresh=True,
        )
    db = db_or_prompt
    if not isinstance(db, Session):
        return chat_model(
            prompt, output_type=SagEventExtractionOutput,
            purpose="sag_event_extract", fresh=True,
        )
    return chat_model(
        prompt, db=db, output_type=SagEventExtractionOutput,
        purpose="sag_event_extract", fresh=True,
    )


def _ollama_event_prompt(chunk: KbChunk, f: FileModel) -> str:
    doc_title = f.original_name or f.filename or "document"
    return (
        "Extract one event and its entities from the chunk. "
        'Return JSON only: {"title":"...","summary":"...","content":"...",'
        '"entities":[{"name":"...","type":"person|org|metric|concept|location|other"}]}. '
        "Use concise canonical Chinese or English names.\n\n"
        f"Document: {doc_title}\n\nChunk:\n{(chunk.text or '')[:_MAX_LLM_CHARS]}"
    )


def extract_ollama_event_for_chunk(
    db: Session,
    chunk: KbChunk,
    f: FileModel,
) -> tuple[dict[str, Any], list[dict[str, str]]] | None:
    parsed = _ollama_chat_json(db, _ollama_event_prompt(chunk, f))
    if not parsed:
        return None
    if not isinstance(parsed, SagEventExtractionOutput):
        try:
            parsed = SagEventExtractionOutput.model_validate(parsed)
        except Exception:
            logger.warning("SAG event structured output invalid")
            return None

    title = _normalize_entity_name(parsed.title) or _rule_title(chunk, f)
    if len(title) > 512:
        title = title[:512]
    summary = parsed.summary.strip() or _first_sentence(chunk.text or "") or title
    content = parsed.content.strip() or (chunk.text or title)

    entities: list[dict[str, str]] = []
    for ent in parsed.entities:
        name = _normalize_entity_name(ent.name)
        if not name:
            continue
        etype = ent.type.lower()
        entities.append({"entity_name": name, "entity_type": etype})
    entities.extend(_heading_path_entities(chunk))

    return (
        {
            "title": title,
            "summary": summary,
            "content": content,
            "extract_layer": "ollama",
        },
        _dedupe_entities(entities),
    )


def _persist_event(
    db: Session,
    f: FileModel,
    chunk: KbChunk,
    event_row: dict[str, Any],
    entity_rows: list[dict[str, str]],
) -> None:
    event = KbEvent(
        user_id=f.user_id,
        workspace_id=f.workspace_id,
        file_id=f.id,
        chunk_id=int(chunk.id),
        title=event_row["title"],
        summary=event_row.get("summary") or "",
        content=event_row["content"],
        extract_layer=event_row["extract_layer"],
    )
    db.add(event)
    db.flush()
    for row in entity_rows:
        db.add(
            KbEventEntity(
                event_id=int(event.id),
                file_id=f.id,
                workspace_id=f.workspace_id,
                entity_name=row["entity_name"],
                entity_type=row.get("entity_type") or "concept",
            )
        )


def rebuild_sag_events_for_file(db: Session, f: FileModel) -> int:
    """Delete and rebuild SAG events for one file after chunk indexing."""
    delete_sag_events_for_file(db, f.id)
    if not is_kb_sag_event_extract_enabled(db):
        return 0

    chunks = (
        db.query(KbChunk)
        .filter(KbChunk.file_id == f.id)
        .order_by(KbChunk.chunk_index)
        .all()
    )
    if not chunks:
        return 0

    mode = get_kb_sag_event_extract_mode(db)
    count = 0
    for chunk in chunks:
        if mode == "ollama":
            extracted = extract_ollama_event_for_chunk(db, chunk, f)
            if extracted is None:
                event_row, entity_rows = extract_rule_event_for_chunk(chunk, f)
            else:
                event_row, entity_rows = extracted
        else:
            event_row, entity_rows = extract_rule_event_for_chunk(chunk, f)
        _persist_event(db, f, chunk, event_row, entity_rows)
        count += 1
    return count
