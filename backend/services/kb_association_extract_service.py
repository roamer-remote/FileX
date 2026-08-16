# Copyright (c) 2026 徐泽宇
"""144: independent full-document association fact extraction."""

from __future__ import annotations

import hashlib
import json
import logging
import re

from sqlalchemy.orm import Session

from models.file import File as FileModel
from models.kb_association import (
    KbAssociationIndexState,
    KbEntity,
    KbEntityAlias,
    KbEntityMention,
    KbEvidenceClaim,
)
from models.kb_chunk import KbChunk
from services.kb_association_claim_service import delete_association_artifacts_for_file
from services.kb_association_version import (
    ASSOCIATION_EXTRACTOR_VERSION,
    association_content_fingerprint,
    association_source_fingerprint,
)
from services.kb_entity_extract_service import extract_rule_entities
from services.kb_post_llm_service import chat_json

logger = logging.getLogger(__name__)
_STABLE_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ASSOCIATION_LLM_BATCH_CHARS = 40000


def _normalize(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _identity_key(value: str) -> str | None:
    text = value.strip()
    return f"email:{text.casefold()}" if _STABLE_EMAIL_RE.match(text) else None


def _locator(chunk: KbChunk | None, *, excerpt: str = "") -> dict | None:
    if chunk is None or not chunk.text:
        return None
    locator = {
        "chunk_id": int(chunk.id),
        "heading_path": chunk.heading_path,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "text_sha256": hashlib.sha256(chunk.text.encode()).hexdigest(),
    }
    if excerpt:
        locator["excerpt"] = excerpt
        locator["excerpt_sha256"] = hashlib.sha256(excerpt.encode()).hexdigest()
        offset = chunk.text.find(excerpt)
        if offset >= 0:
            context = chunk.text[max(0, offset - 96) : min(len(chunk.text), offset + len(excerpt) + 96)]
            normalized_context = " ".join(context.split())
            locator["hash_mode"] = "excerpt_context_v1"
            locator["context_excerpt"] = context
            locator["context_sha256"] = hashlib.sha256(normalized_context.encode()).hexdigest()
    return locator


def _association_llm_rows(db: Session, chunks: list[KbChunk]) -> list[dict]:
    """Ask for claims with a verifiable source chunk and literal excerpt."""
    input_segments: list[tuple[int, str]] = []
    segment_chars = ASSOCIATION_LLM_BATCH_CHARS - 128
    for chunk in chunks:
        text = str(chunk.text or "")
        for offset in range(0, len(text), max(1, segment_chars)):
            input_segments.append((int(chunk.id), text[offset : offset + segment_chars]))
    if not input_segments:
        return []
    rows: list[dict] = []
    batch: list[tuple[int, str]] = []
    batch_chars = 0

    def extract_batch(batch_chunks: list[tuple[int, str]]) -> None:
        if not batch_chunks:
            return
        prompt = (
            "Extract document-local association claims. Return JSON only: "
            '{"claims":[{"source":"...","source_type":"person|org|concept|other",'
            '"predicate":"...","target":"...","qualifiers":{},"source_chunk_id":123,"excerpt":"exact text"}]}. '
            "Each excerpt must be a literal substring of its source chunk; omit any claim that cannot be located.\n\n"
            + "\n\n".join(f"[chunk:{chunk_id}]\n{text}" for chunk_id, text in batch_chunks)
        )
        try:
            parsed = chat_json(prompt, db=db, purpose="entity_extract", fresh=True) or {}
        except Exception as exc:  # optional enrichment is fail-open
            logger.warning("association LLM batch failed; preserving rule rows: %s", exc)
            return
        chunk_texts = {int(chunk.id): str(chunk.text or "") for chunk in chunks}
        for claim in parsed.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            source = str(claim.get("source") or "").strip()
            target = str(claim.get("target") or "").strip()
            excerpt = str(claim.get("excerpt") or "").strip()
            chunk_id = claim.get("source_chunk_id")
            if (
                not source
                or not excerpt
                or not isinstance(chunk_id, int)
                or excerpt not in chunk_texts.get(chunk_id, "")
            ):
                continue
            rows.append({
                "entity_name": source, "entity_type": str(claim.get("source_type") or "concept"),
                "relation": str(claim.get("predicate") or "related_to"), "target_entity_name": target or None,
                "source_chunk_id": chunk_id, "extract_layer": "llm", "excerpt": excerpt,
                "qualifiers": claim.get("qualifiers") if isinstance(claim.get("qualifiers"), dict) else {},
            })

    for chunk_id, text in input_segments:
        size = len(text) + 32
        if batch and batch_chars + size > ASSOCIATION_LLM_BATCH_CHARS:
            extract_batch(batch)
            batch = []
            batch_chars = 0
        batch.append((chunk_id, text))
        batch_chars += size
    extract_batch(batch)
    unique: dict[tuple[str, ...], dict] = {}
    for row in rows:
        key = (
            int(row["source_chunk_id"]),
            _normalize(str(row["entity_name"])),
            _normalize(str(row.get("relation") or "")),
            _normalize(str(row.get("target_entity_name") or "")),
            json.dumps(row.get("qualifiers") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            hashlib.sha256(str(row.get("excerpt") or "").encode()).hexdigest(),
        )
        unique[key] = row
    return list(unique.values())


def _resolved_entity(
    db: Session, f: FileModel, *, name: str, entity_type: str
) -> KbEntity | None:
    """Return a canonical entity only when the source supplies a stable identity.

    Normalized names are useful search keys but are never an identity proof.  In
    particular, two resumes containing the same Chinese name must not form a
    graph bridge merely because their text normalizes to the same value.
    """
    identity_key = _identity_key(name)
    if identity_key is None:
        return None
    normalized = _normalize(name)
    entity = (
        db.query(KbEntity)
        .filter(
            KbEntity.workspace_id == f.workspace_id,
            KbEntity.entity_type == entity_type,
            KbEntity.identity_key == identity_key,
        )
        .first()
    )
    if entity is None:
        entity = KbEntity(
            workspace_id=f.workspace_id,
            entity_type=entity_type,
            canonical_name=name[:512],
            normalized_name=normalized[:512],
            identity_key=identity_key,
        )
        db.add(entity)
        db.flush()
    return entity


def _mention(
    db: Session,
    f: FileModel,
    *,
    entity: KbEntity | None,
    name: str,
    entity_type: str,
    source_chunk_id: int | None,
    extract_layer: str | None,
    source_locator: dict | None,
) -> KbEntityMention:
    stable = _identity_key(name)
    mention = KbEntityMention(
        user_id=f.user_id,
        workspace_id=f.workspace_id,
        file_id=f.id,
        entity_id=entity.id if entity is not None else None,
        entity_type=entity_type,
        surface=name[:512],
        normalized_surface=_normalize(name)[:512],
        resolution_status="resolved" if entity is not None and stable else "unresolved",
        resolution_confidence=1.0 if stable else None,
        source_chunk_id=source_chunk_id,
        source_locator=source_locator,
        extract_layer=extract_layer,
    )
    db.add(mention)
    db.flush()
    return mention


def rebuild_association_facts_for_file(db: Session, f: FileModel) -> int:
    """Rebuild one file's facts independently of the optional post-processing path."""
    if f.workspace_id is None:
        logger.warning("kb association extraction skipped file without workspace file_id=%s", f.id)
        return 0
    source_fingerprint = association_source_fingerprint(f)
    content_fingerprint = association_content_fingerprint(f)
    state = db.query(KbAssociationIndexState).filter_by(file_id=f.id).first()
    next_attempt_count = int(state.attempt_count or 0) + 1 if state is not None else 1
    if state is None:
        state = KbAssociationIndexState(file_id=f.id, workspace_id=f.workspace_id, status="running")
        db.add(state)
    else:
        state.workspace_id = f.workspace_id
        state.status = "running"
        state.last_error = None
    state.source_fingerprint = source_fingerprint or None
    state.extractor_version = ASSOCIATION_EXTRACTOR_VERSION
    state.content_fingerprint = content_fingerprint
    state.attempt_count = next_attempt_count
    db.flush()
    try:
        delete_association_artifacts_for_file(db, f.id)
        state = KbAssociationIndexState(
            file_id=f.id,
            workspace_id=f.workspace_id,
            source_fingerprint=source_fingerprint or None,
            extractor_version=ASSOCIATION_EXTRACTOR_VERSION,
            content_fingerprint=content_fingerprint,
            status="running",
            attempt_count=next_attempt_count,
        )
        db.add(state)
        chunks = (
            db.query(KbChunk).filter(KbChunk.file_id == f.id).order_by(KbChunk.chunk_index).all()
        )
        chunks_by_id = {int(chunk.id): chunk for chunk in chunks}
        # The extractor receives document-level text, not just retrieval top-k.
        full_text = "\n\n".join(chunk.text for chunk in chunks if chunk.text)
        rows = extract_rule_entities(chunks)
        if full_text:
            rows.extend(_association_llm_rows(db, chunks))
        mentions: dict[tuple[str, str], KbEntityMention] = {}
        claim_count = 0
        for row in rows:
            source = str(row.get("entity_name") or "").strip()
            target = str(row.get("target_entity_name") or "").strip()
            entity_type = str(row.get("entity_type") or "concept").lower()[:32]
            if not source:
                continue
            source_key = (entity_type, _normalize(source))
            source_chunk_id = row.get("source_chunk_id")
            source_chunk = chunks_by_id.get(int(source_chunk_id)) if source_chunk_id else None
            excerpt = str(row.get("excerpt") or "").strip()
            if excerpt and (source_chunk is None or excerpt not in source_chunk.text):
                continue
            source_locator = _locator(source_chunk, excerpt=excerpt)
            if source_locator is None:
                # A fact without an original-document position cannot participate
                # in a conclusion that must be independently verified.
                continue
            source_mention = mentions.get(source_key)
            if source_mention is None:
                source_mention = _mention(
                    db, f, entity=_resolved_entity(db, f, name=source, entity_type=entity_type),
                    name=source, entity_type=entity_type, source_chunk_id=source_chunk_id,
                    extract_layer=row.get("extract_layer"), source_locator=source_locator,
                )
                mentions[source_key] = source_mention
                if source_mention.entity_id is not None:
                    db.add(KbEntityAlias(
                        entity_id=source_mention.entity_id, mention_id=source_mention.id,
                        source_file_id=f.id, normalized_alias=source_mention.normalized_surface,
                    ))
            target_mention = None
            if target:
                target_key = ("concept", _normalize(target))
                target_mention = mentions.get(target_key)
                if target_mention is None:
                    target_mention = _mention(
                        db, f, entity=_resolved_entity(db, f, name=target, entity_type="concept"),
                        name=target, entity_type="concept", source_chunk_id=source_chunk_id,
                        extract_layer=row.get("extract_layer"), source_locator=source_locator,
                    )
                    mentions[target_key] = target_mention
            predicate = str(row.get("relation") or "mentions").strip()[:96] or "mentions"
            qualifier_key = json.dumps(
                row.get("qualifiers") if isinstance(row.get("qualifiers"), dict) else {},
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            )
            digest = hashlib.sha256(
                "|".join((source_fingerprint, _normalize(source), predicate, _normalize(target), qualifier_key, source_locator["text_sha256"], excerpt)).encode()
            ).hexdigest()
            db.add(
                KbEvidenceClaim(
                    user_id=f.user_id, workspace_id=f.workspace_id, file_id=f.id,
                    subject_mention_id=source_mention.id, object_mention_id=target_mention.id if target_mention else None,
                    predicate=predicate, source_chunk_id=source_chunk_id, source_locator=source_locator,
                    extract_layer=row.get("extract_layer"), confidence=0.9 if row.get("extract_layer") == "llm" else 0.7,
                    claim_hash=digest, qualifiers=row.get("qualifiers") if isinstance(row.get("qualifiers"), dict) else None,
                )
            )
            claim_count += 1
        state.status = "ready"
        state.last_error = None
        return claim_count
    except Exception as exc:
        logger.exception("kb association extraction failed file_id=%s", f.id)
        state.status = "failed"
        state.last_error = str(exc)[:2000]
        raise
