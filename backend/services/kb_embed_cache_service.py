# Copyright (c) 2026 徐泽宇
"""Embed input hash cache (061 P0-A)."""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Callable
from typing import Iterable

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from config import KB_EMBED_CACHE_ENABLED
from services.ollama_config_service import get_ollama_runtime_config
from services.system_setting_service import get_kb_embed_cache_enabled
from models.kb_embedding_cache import KbEmbeddingCache
from services.kb_ollama_embed import embed_texts

import logging

logger = logging.getLogger(__name__)


def hash_embed_input(text: str) -> str:
    """Normalization: NFC + strip + SHA256 hex."""
    normalized = unicodedata.normalize("NFC", (text or "").strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def enabled(db: Session | None = None) -> bool:
    if db is not None:
        try:
            return get_kb_embed_cache_enabled(db)
        except Exception as exc:
            logger.warning("kb_embed_cache_enabled fallback to env: %s", exc)
    return KB_EMBED_CACHE_ENABLED


def lookup_many(db: Session, hashes: Iterable[str], model: str) -> dict[str, list[float]]:
    unique = list(dict.fromkeys(hashes))
    if not unique:
        return {}
    rows = (
        db.query(KbEmbeddingCache.embed_input_hash, KbEmbeddingCache.embedding)
        .filter(
            KbEmbeddingCache.embedding_model == model,
            KbEmbeddingCache.embed_input_hash.in_(unique),
        )
        .all()
    )
    return {h: list(vec) for h, vec in rows}


def put_many(
    db: Session,
    entries: Iterable[tuple[str, str, list[float]]],
) -> None:
    deduped: dict[tuple[str, str], list[float]] = {}
    for h, model, vec in entries:
        deduped[(h, model)] = vec
    payload = [
        {
            "embed_input_hash": h,
            "embedding_model": model,
            "embedding": vec,
        }
        for (h, model), vec in deduped.items()
    ]
    if not payload:
        return
    stmt = insert(KbEmbeddingCache).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["embed_input_hash", "embedding_model"],
        set_={"embedding": stmt.excluded.embedding},
    )
    db.execute(stmt)


def resolve_embedding_vectors(
    db: Session,
    embed_inputs: list[str],
    *,
    heartbeat_cb: Callable[[], None] | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    """Resolve vectors: cache lookup, embed misses only, upsert new rows."""
    if not embed_inputs:
        return []
    total = len(embed_inputs)
    if not enabled(db):
        return embed_texts(
            embed_inputs,
            heartbeat_cb=heartbeat_cb,
            progress_cb=progress_cb,
        )

    model = get_ollama_runtime_config(db, fresh=True).embed_model
    hashes = [hash_embed_input(text) for text in embed_inputs]
    cached = lookup_many(db, hashes, model)

    miss_indices = [i for i, h in enumerate(hashes) if h not in cached]
    cache_hits = total - len(miss_indices)
    if progress_cb is not None and cache_hits:
        progress_cb(cache_hits, total)
    if miss_indices:
        miss_texts = [embed_inputs[i] for i in miss_indices]

        def _miss_progress(done: int, miss_total: int) -> None:
            if progress_cb is not None:
                progress_cb(cache_hits + done, total)

        new_vectors = embed_texts(
            miss_texts,
            heartbeat_cb=heartbeat_cb,
            progress_cb=_miss_progress,
        )
        put_many(
            db,
            [(hashes[i], model, new_vectors[j]) for j, i in enumerate(miss_indices)],
        )
        for j, i in enumerate(miss_indices):
            cached[hashes[i]] = new_vectors[j]

    return [cached[h] for h in hashes]
