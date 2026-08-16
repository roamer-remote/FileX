# Copyright (c) 2026 徐泽宇
"""RAGAS-only Chat LLM runtime configuration."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from database import SessionLocal
from models.system_setting import SystemSetting
from services.system_setting_service import (
    DEFAULTS,
    KEY_KB_RAGAS_LLM_API_KEY,
    KEY_KB_RAGAS_LLM_BASE_URL,
    KEY_KB_RAGAS_LLM_MODEL,
    KEY_KB_RAGAS_LLM_PROVIDER,
    KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS,
    secret_credential_from_stored,
)

RagasLlmProvider = Literal["ollama", "openai_compatible"]

_runtime_cache: RagasLlmRuntimeConfig | None = None
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class RagasLlmRuntimeConfig:
    provider: RagasLlmProvider
    base_url: str
    model: str
    api_key: str | None
    timeout_seconds: int
    is_configured: bool
    unconfigured_reason: str | None = None


def invalidate_ragas_llm_runtime_cache() -> None:
    global _runtime_cache
    with _cache_lock:
        _runtime_cache = None


def _read_settings(db: Session) -> dict[str, str]:
    keys = (
        KEY_KB_RAGAS_LLM_PROVIDER,
        KEY_KB_RAGAS_LLM_BASE_URL,
        KEY_KB_RAGAS_LLM_MODEL,
        KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS,
        KEY_KB_RAGAS_LLM_API_KEY,
    )
    rows = (
        db.query(SystemSetting)
        .filter(SystemSetting.setting_key.in_(keys))
        .all()
    )
    return {key: next((row.value for row in rows if row.setting_key == key), DEFAULTS[key]) for key in keys}


def _parse_provider(raw: object) -> RagasLlmProvider:
    return "openai_compatible" if str(raw or "").strip().lower() == "openai_compatible" else "ollama"


def _parse_timeout(raw: object) -> int:
    try:
        return max(10, min(300, int(str(raw).strip())))
    except ValueError:
        return int(DEFAULTS[KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS])


def _runtime_from_db(db: Session) -> RagasLlmRuntimeConfig:
    settings = _read_settings(db)
    provider = _parse_provider(settings[KEY_KB_RAGAS_LLM_PROVIDER])
    base_url = str(settings[KEY_KB_RAGAS_LLM_BASE_URL] or "").strip().rstrip("/")
    model = str(settings[KEY_KB_RAGAS_LLM_MODEL] or "").strip()
    api_key = secret_credential_from_stored(settings[KEY_KB_RAGAS_LLM_API_KEY]) or None
    if not base_url or not model:
        reason = "base_url_and_model_required"
    elif provider == "openai_compatible" and not api_key:
        reason = "api_key_required"
    else:
        reason = None
    return RagasLlmRuntimeConfig(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=_parse_timeout(settings[KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS]),
        is_configured=reason is None,
        unconfigured_reason=reason,
    )


def get_ragas_llm_runtime_config(
    db: Session | None = None, *, fresh: bool = False
) -> RagasLlmRuntimeConfig:
    global _runtime_cache
    if not fresh:
        with _cache_lock:
            if _runtime_cache is not None:
                return _runtime_cache

    owns_session = db is None
    session = db or SessionLocal()
    try:
        loaded = _runtime_from_db(session)
    finally:
        if owns_session:
            session.close()

    with _cache_lock:
        _runtime_cache = loaded
    return loaded
