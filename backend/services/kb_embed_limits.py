# Copyright (c) 2026 徐泽宇
"""Embedder character limits for KB chunk sizing (061 P0-C)."""

from __future__ import annotations

import os

from services.ollama_config_service import get_ollama_runtime_config

_MODEL_MAX_CHARS: dict[str, int] = {
    "bge-m3": 8192,
    "bge-m3:latest": 8192,
}


def _env_embed_max_chars() -> int:
    raw = os.environ.get("OLLAMA_EMBED_MAX_CHARS")
    if raw is not None and str(raw).strip():
        try:
            return max(1, int(str(raw).strip()))
        except ValueError:
            pass
    return 8192


def max_chars_for_model(model: str) -> int:
    key = (model or "").strip()
    if not key:
        return _env_embed_max_chars()
    if key in _MODEL_MAX_CHARS:
        return _MODEL_MAX_CHARS[key]
    base = key.split(":")[0]
    if base in _MODEL_MAX_CHARS:
        return _MODEL_MAX_CHARS[base]
    return _env_embed_max_chars()


def effective_max_chars_for_current_model() -> int:
    return max_chars_for_model(get_ollama_runtime_config(fresh=True).embed_model)
