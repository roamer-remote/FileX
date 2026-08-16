# Copyright (c) 2026 徐泽宇
"""RAGAS-only Chat LLM runtime configuration tests."""

from services.kb_ragas_llm_service import get_ragas_llm_runtime_config
from services.system_setting_service import (
    KEY_KB_RAGAS_LLM_API_KEY,
    KEY_KB_RAGAS_LLM_BASE_URL,
    KEY_KB_RAGAS_LLM_MODEL,
    KEY_KB_RAGAS_LLM_PROVIDER,
    KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS,
    update_settings,
)


def test_openai_runtime_reads_only_ragas_settings(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_RAGAS_LLM_PROVIDER: "openai_compatible",
            KEY_KB_RAGAS_LLM_BASE_URL: "https://ragas.example.com/v1",
            KEY_KB_RAGAS_LLM_MODEL: "ragas-model",
            KEY_KB_RAGAS_LLM_API_KEY: "sk-ragas",
            KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS: "75",
        },
    )

    cfg = get_ragas_llm_runtime_config(db_session, fresh=True)

    assert cfg.is_configured is True
    assert cfg.provider == "openai_compatible"
    assert cfg.base_url == "https://ragas.example.com/v1"
    assert cfg.model == "ragas-model"
    assert cfg.api_key == "sk-ragas"
    assert cfg.timeout_seconds == 75


def test_runtime_marks_incomplete_ollama_settings_unconfigured(db_session):
    cfg = get_ragas_llm_runtime_config(db_session, fresh=True)

    assert cfg.provider == "ollama"
    assert cfg.is_configured is False
    assert cfg.unconfigured_reason == "base_url_and_model_required"


def test_fresh_runtime_observes_updated_ragas_model(db_session):
    update_settings(
        db_session,
        {
            KEY_KB_RAGAS_LLM_PROVIDER: "ollama",
            KEY_KB_RAGAS_LLM_BASE_URL: "http://ragas-ollama:11434",
            KEY_KB_RAGAS_LLM_MODEL: "model-a",
        },
    )
    assert get_ragas_llm_runtime_config(db_session, fresh=True).model == "model-a"

    update_settings(db_session, {KEY_KB_RAGAS_LLM_MODEL: "model-b"})
    assert get_ragas_llm_runtime_config(db_session, fresh=True).model == "model-b"
