# Copyright (c) 2026 徐泽宇
"""030 P3: per-document entity extraction (rule + optional Ollama JSON)."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_doc_entity_edge import KbDocEntityEdge
from schemas.llm_outputs import EntityExtractionOutput
from services.kb_post_llm_service import chat_model
from services.system_setting_service import is_kb_entity_extract_enabled
from services.wiki_provenance_service import provenance_dict

logger = logging.getLogger(__name__)

_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
_ENTITY_TYPES = frozenset({"person", "org", "metric", "concept", "location", "other"})
_MAX_LLM_CHARS = 12000


def delete_doc_entity_edges_for_file(db: Session, file_id: int) -> None:
    db.query(KbDocEntityEdge).filter(KbDocEntityEdge.file_id == file_id).delete()


def _normalize_entity_name(name: str) -> str | None:
    cleaned = " ".join(str(name).strip().split())
    if not cleaned or len(cleaned) > 256:
        return None
    return cleaned


def _parse_table_header_cells(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header_line = lines[0]
    if not header_line.startswith("|"):
        return []
    if not _TABLE_SEP_RE.match(lines[1]):
        return []
    cells = [c.strip() for c in header_line.strip("|").split("|")]
    return [c for c in cells if c]


def _rule_edges_for_chunk(chunk: KbChunk) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    block_type = (chunk.block_type or "").lower()
    content_kind = (getattr(chunk, "content_kind", None) or "").lower()
    meta = chunk.content_meta if isinstance(chunk.content_meta, dict) else {}

    if block_type == "table" or content_kind == "table":
        for cell in _parse_table_header_cells(chunk.text or ""):
            name = _normalize_entity_name(cell)
            if name:
                edges.append(
                    {
                        "entity_name": name,
                        "entity_type": "metric" if any(ch.isdigit() for ch in name) else "concept",
                        "relation": "column_header",
                        "target_entity_name": None,
                        "source_chunk_id": int(chunk.id),
                        "extract_layer": "rule",
                    }
                )

    caption = meta.get("caption")
    if caption:
        cap = _normalize_entity_name(str(caption))
        if cap:
            kind = (content_kind or "concept").lower()
            entity_type = "metric" if kind == "table" else "concept"
            edges.append(
                {
                    "entity_name": cap,
                    "entity_type": entity_type if entity_type in _ENTITY_TYPES else "concept",
                    "relation": "caption",
                    "target_entity_name": None,
                    "source_chunk_id": int(chunk.id),
                    "extract_layer": "rule",
                }
            )

    return edges


def extract_rule_entities(chunks: list[KbChunk]) -> list[dict[str, Any]]:
    seen: set[tuple[int, str, str | None]] = set()
    out: list[dict[str, Any]] = []
    for chunk in chunks:
        for edge in _rule_edges_for_chunk(chunk):
            key = (
                int(edge["source_chunk_id"]),
                edge["entity_name"],
                edge.get("relation"),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(edge)
    return out


def _ollama_chat_json(
    db_or_prompt: Session | str, prompt: str | None = None
) -> EntityExtractionOutput | None:
    if prompt is None:
        return chat_model(
            str(db_or_prompt), output_type=EntityExtractionOutput,
            purpose="entity_extract", fresh=True,
        )
    db = db_or_prompt
    if not isinstance(db, Session):
        return chat_model(
            prompt, output_type=EntityExtractionOutput,
            purpose="entity_extract", fresh=True,
        )
    return chat_model(
        prompt, db=db, output_type=EntityExtractionOutput,
        purpose="entity_extract", fresh=True,
    )


def _llm_prompt(text: str) -> str:
    return (
        "Extract named entities and relations from the document excerpt. "
        'Return JSON only: {"entities":[{"name":"...","type":"person|org|metric|concept|location|other"}],'
        '"relations":[{"source":"...","relation":"mentions|part_of|...","target":"..."}]}. '
        "Use concise canonical Chinese or English names.\n\n"
        f"{text[:_MAX_LLM_CHARS]}"
    )


def extract_llm_entities(
    db: Session,
    *,
    chunks: list[KbChunk],
    full_text: str,
) -> list[dict[str, Any]]:
    if not is_kb_entity_extract_enabled(db):
        return []

    default_chunk_id = int(chunks[0].id) if chunks else None
    parsed = _ollama_chat_json(db, _llm_prompt(full_text))
    if not parsed:
        return []
    if not isinstance(parsed, EntityExtractionOutput):
        try:
            parsed = EntityExtractionOutput.model_validate(parsed)
        except Exception:
            logger.warning("entity extraction structured output invalid")
            return []

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str | None]] = set()

    for ent in parsed.entities:
        name = _normalize_entity_name(ent.name)
        if not name:
            continue
        etype = ent.type.lower()
        if etype not in _ENTITY_TYPES:
            etype = "other"
        key = (name, "mentions", None)
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            {
                "entity_name": name,
                "entity_type": etype,
                "relation": "mentions",
                "target_entity_name": None,
                "source_chunk_id": default_chunk_id,
                "extract_layer": "llm",
            }
        )

    for rel in parsed.relations:
        source = _normalize_entity_name(rel.source)
        target = _normalize_entity_name(rel.target or "")
        if not source:
            continue
        relation = rel.relation.strip()[:64]
        key = (source, relation, target)
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            {
                "entity_name": source,
                "entity_type": "concept",
                "relation": relation,
                "target_entity_name": target,
                "source_chunk_id": default_chunk_id,
                "extract_layer": "llm",
            }
        )

    return edges


def _persist_edges(
    db: Session,
    f: FileModel,
    edge_rows: list[dict[str, Any]],
) -> int:
    count = 0
    for row in edge_rows:
        prov = provenance_dict(provenance="extracted", confidence=0.9, source_kind="search_hit")
        db.add(
            KbDocEntityEdge(
                user_id=f.user_id,
                workspace_id=f.workspace_id,
                file_id=f.id,
                entity_name=row["entity_name"],
                entity_type=row.get("entity_type") or "concept",
                relation=row.get("relation"),
                target_entity_name=row.get("target_entity_name"),
                source_chunk_id=row.get("source_chunk_id"),
                provenance=prov,
                extract_layer=row.get("extract_layer"),
            )
        )
        count += 1
    return count


def rebuild_doc_entity_edges_for_file(db: Session, f: FileModel) -> int:
    """Delete and rebuild entity edges for one file after chunk indexing."""
    delete_doc_entity_edges_for_file(db, f.id)
    chunks = (
        db.query(KbChunk)
        .filter(KbChunk.file_id == f.id)
        .order_by(KbChunk.chunk_index)
        .all()
    )
    if not chunks:
        return 0

    rule_edges = extract_rule_entities(chunks)
    full_text = "\n\n".join(c.text for c in chunks if c.text)
    llm_edges: list[dict[str, Any]] = []
    try:
        llm_edges = extract_llm_entities(db, chunks=chunks, full_text=full_text)
    except Exception:
        logger.exception("kb_entity_extract llm failed file_id=%s", f.id)
    return _persist_edges(db, f, rule_edges + llm_edges)
