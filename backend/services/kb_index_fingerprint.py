# Copyright (c) 2026 徐泽宇
"""Index pipeline fingerprint (061 P0-B/P0-C)."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from config import OLLAMA_EMBED_MODEL
from models.file import File as FileModel
from services.kb_chunk_embed_input import EMBED_HEADER_VERSION
from services.kb_chunk_ops_service import compute_index_source_hash
from services.kb_chunk_profile import resolve_effective_chunk_params
from services.kb_text_source import resolve_index_text
from services.ollama_config_service import get_ollama_runtime_config
from services.user_setting_service import get_user_effective_dict
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_FINGERPRINT_PAYLOAD_KEYS = (
    "text_hash",
    "profile_name",
    "chunk_size",
    "chunk_overlap",
    "embed_header_version",
    "embedding_model",
    "sag_extract_enabled",
    "sag_extract_mode",
    "sag_prompt_version",
    "sag_embed_enabled",
)


def fingerprint_payload(
    *,
    text_hash: str,
    profile_name: str,
    chunk_size: int,
    chunk_overlap: int,
    embed_header_version: int = EMBED_HEADER_VERSION,
    embedding_model: str = OLLAMA_EMBED_MODEL,
    sag_extract_enabled: bool = False,
    sag_extract_mode: str = "rule",
    sag_prompt_version: int = 1,
    sag_embed_enabled: bool = False,
) -> dict[str, Any]:
    return {
        "text_hash": text_hash,
        "profile_name": profile_name,
        "chunk_size": int(chunk_size),
        "chunk_overlap": int(chunk_overlap),
        "embed_header_version": int(embed_header_version),
        "embedding_model": embedding_model,
        "sag_extract_enabled": bool(sag_extract_enabled),
        "sag_extract_mode": str(sag_extract_mode),
        "sag_prompt_version": int(sag_prompt_version),
        "sag_embed_enabled": bool(sag_embed_enabled),
    }


def fingerprint_canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_index_pipeline_fingerprint(
    *,
    text_hash: str,
    profile_name: str,
    chunk_size: int,
    chunk_overlap: int,
    embed_header_version: int = EMBED_HEADER_VERSION,
    embedding_model: str = OLLAMA_EMBED_MODEL,
    sag_extract_enabled: bool = False,
    sag_extract_mode: str = "rule",
    sag_prompt_version: int = 1,
    sag_embed_enabled: bool = False,
) -> str:
    payload = fingerprint_payload(
        text_hash=text_hash,
        profile_name=profile_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embed_header_version=embed_header_version,
        embedding_model=embedding_model,
        sag_extract_enabled=sag_extract_enabled,
        sag_extract_mode=sag_extract_mode,
        sag_prompt_version=sag_prompt_version,
        sag_embed_enabled=sag_embed_enabled,
    )
    return hashlib.sha256(fingerprint_canonical_json(payload).encode("utf-8")).hexdigest()


def parse_stored_fingerprint_payload(raw: str | None) -> dict[str, Any] | None:
    if not raw or not str(raw).strip():
        return None
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def describe_fingerprint_field_diff(
    old: dict[str, Any] | None,
    new: dict[str, Any],
) -> str:
    if not old:
        return "stored_payload_unavailable"
    parts: list[str] = []
    for key in _FINGERPRINT_PAYLOAD_KEYS:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            parts.append(f"{key} {old_val}→{new_val}")
    return ", ".join(parts) if parts else "hash_only_change"


def build_text_to_chunk(f: FileModel, text: str) -> str:
    if f.original_name:
        return f"【{f.original_name}】\n\n{text}"
    return text


def compute_file_fingerprint(
    db: Session,
    f: FileModel,
    *,
    effective: dict[str, str] | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    text, _ = resolve_index_text(f)
    if not text:
        return None, None
    text_to_chunk = build_text_to_chunk(f, text)
    text_hash = compute_index_source_hash(text_to_chunk)
    if effective is None:
        effective = get_user_effective_dict(db, f.user_id)
    params = resolve_effective_chunk_params(db, f, effective=effective, md_char_count=len(text))
    from services.system_setting_service import get_kb_sag_event_fingerprint_fields

    payload = fingerprint_payload(
        text_hash=text_hash,
        profile_name=params.profile_name,
        chunk_size=params.chunk_size,
        chunk_overlap=params.overlap,
        embedding_model=get_ollama_runtime_config(db).embed_model,
        **get_kb_sag_event_fingerprint_fields(db),
    )
    return compute_index_pipeline_fingerprint(**payload), payload


def log_fingerprint_mismatch(
    f: FileModel,
    *,
    computed_fingerprint: str,
    payload: dict[str, Any],
) -> None:
    stored_payload = parse_stored_fingerprint_payload(getattr(f, "index_fingerprint_payload", None))
    diff = describe_fingerprint_field_diff(stored_payload, payload)
    logger.info(
        "kb_index_fingerprint_mismatch file_id=%s stored=%s computed=%s diff=%s",
        f.id,
        f.index_pipeline_fingerprint,
        computed_fingerprint,
        diff,
    )
