# Copyright (c) 2026 徐泽宇
"""Chunking profiles (system default + MIME hints).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from dataclasses import dataclass

from config import KB_CHUNK_OVERLAP, KB_CHUNK_SIZE, KB_CHUNK_USE_STRUCTURE
from services.kb_embed_limits import max_chars_for_model
from services.ollama_config_service import get_ollama_runtime_config
from services.system_setting_service import (
    get_kb_chunk_overlap,
    get_kb_chunk_profile,
    get_kb_chunk_size,
    get_kb_chunk_split_recursive,
)

VALID_PROFILES = frozenset({"default", "long_doc", "qa_pairs", "table_heavy"})

# T-4 large document threshold (md chars after extraction)
LARGE_DOC_CHAR_THRESHOLD = 400_000
LARGE_DOC_CHUNK_SIZE = 1800
LARGE_DOC_CHUNK_OVERLAP = 150


@dataclass(frozen=True)
class ChunkProfileParams:
    """分块配置params 业务服务。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-25

        Attributes:
            name: 名称（str）。
            chunk_size: 分块大小（int）。
            overlap: overlap（int）。
            use_structure: use结构（bool）。
    """
    name: str
    chunk_size: int
    overlap: int
    use_structure: bool


def profile_table_chunk_params(profile_name: str) -> tuple[int, int]:
    profile = _PROFILE_TABLE.get(profile_name) or _PROFILE_TABLE["default"]
    return profile.chunk_size, profile.overlap


_PROFILE_TABLE: dict[str, ChunkProfileParams] = {
    "default": ChunkProfileParams("default", KB_CHUNK_SIZE, KB_CHUNK_OVERLAP, KB_CHUNK_USE_STRUCTURE),
    "long_doc": ChunkProfileParams("long_doc", 1200, 150, True),
    "qa_pairs": ChunkProfileParams("qa_pairs", 512, 64, True),
    "table_heavy": ChunkProfileParams("table_heavy", 600, 80, True),
}


def _mime_profile_hint(mime: str | None, original_name: str | None) -> str | None:
    name = (original_name or "").lower()
    mime_l = (mime or "").lower()
    if name.endswith(".md") or "markdown" in mime_l:
        return None
    if name.endswith((".xlsx", ".xls", ".csv")) or "spreadsheet" in mime_l or "excel" in mime_l:
        return "table_heavy"
    if name.endswith((".ppt", ".pptx")) or "presentation" in mime_l:
        return "long_doc"
    if name.endswith(".pdf") or mime_l == "application/pdf":
        return "long_doc"
    return None


def resolve_chunk_profile(
    db,
    *,
    mime_type: str | None = None,
    original_name: str | None = None,
    override: str | None = None,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> ChunkProfileParams:
    if override and override in VALID_PROFILES:
        return _PROFILE_TABLE[override]
    hint = _mime_profile_hint(mime_type, original_name)
    if hint and hint in _PROFILE_TABLE:
        return _PROFILE_TABLE[hint]
    name = get_kb_chunk_profile(db, user_id=user_id, effective=effective)
    if name not in VALID_PROFILES:
        name = "default"
    return _PROFILE_TABLE[name]


@dataclass(frozen=True)
class EffectiveChunkParams:
    profile_name: str
    chunk_size: int
    overlap: int
    use_structure: bool
    split_recursive: bool
    effective_max_chars: int


def resolve_effective_chunk_params(
    db,
    file,
    *,
    mime_type: str | None = None,
    original_name: str | None = None,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
    md_char_count: int | None = None,
) -> EffectiveChunkParams:
    profile = resolve_chunk_profile(
        db,
        mime_type=mime_type if mime_type is not None else getattr(file, "mime_type", None),
        original_name=original_name if original_name is not None else getattr(file, "original_name", None),
        user_id=user_id if user_id is not None else getattr(file, "user_id", None),
        effective=effective,
    )
    system_size = get_kb_chunk_size(db, user_id=user_id, effective=effective)
    system_overlap = get_kb_chunk_overlap(db, user_id=user_id, effective=effective)
    base_size = profile.chunk_size if system_size is None else system_size
    base_overlap = profile.overlap if system_overlap is None else system_overlap

    # T-4: large PDF / large doc volume-aware chunking (from system settings)
    from services.system_setting_service import get_kb_large_doc_settings
    large = get_kb_large_doc_settings(db)
    if md_char_count and md_char_count > large["char_threshold"]:
        if profile.name in ("long_doc", "default"):
            base_size = max(base_size, large["chunk_size"])
            base_overlap = max(base_overlap, large["chunk_overlap"])

    model_cap = max_chars_for_model(get_ollama_runtime_config(db).embed_model)
    effective_size = min(base_size, model_cap)
    effective_overlap = min(base_overlap, max(0, effective_size - 1))
    split_recursive = get_kb_chunk_split_recursive(db, user_id=user_id, effective=effective)
    return EffectiveChunkParams(
        profile_name=profile.name,
        chunk_size=effective_size,
        overlap=effective_overlap,
        use_structure=profile.use_structure,
        split_recursive=split_recursive,
        effective_max_chars=model_cap,
    )
