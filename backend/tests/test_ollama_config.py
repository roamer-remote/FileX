# Copyright (c) 2026 徐泽宇
"""Ollama system settings and runtime config (069)."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.ollama_config_service import (
    OllamaRuntimeConfig,
    get_ollama_runtime_config,
    invalidate_ollama_runtime_cache,
    probe_ollama,
    validate_ollama_base_url,
)
from services.system_setting_service import (
    KEY_OLLAMA_API_KEY,
    KEY_OLLAMA_EMBED_CONCURRENCY,
    KEY_OLLAMA_NUM_PARALLEL,
    _parse_ollama_embed_concurrency,
    _parse_ollama_num_parallel,
)
from services.system_setting_service import (
    KEY_OLLAMA_BASE_URL,
    KEY_OLLAMA_EMBED_BATCH_SIZE,
    KEY_OLLAMA_EMBED_DIM,
    KEY_OLLAMA_EMBED_MODEL,
    KEY_OLLAMA_TIMEOUT_SEC,
    invalidate_settings_cache,
    update_settings,
)


def test_validate_ollama_base_url_normalizes():
    assert validate_ollama_base_url("http://filex-ollama:11434/") == "http://filex-ollama:11434"


def test_validate_ollama_base_url_rejects_invalid():
    with pytest.raises(ValueError, match="http/https"):
        validate_ollama_base_url("ftp://bad")


def test_ollama_settings_persist_and_runtime(db_session):
    update_settings(
        db_session,
        {
            KEY_OLLAMA_BASE_URL: "http://ollama.test:11434",
            KEY_OLLAMA_EMBED_MODEL: "bge-m3:latest",
            KEY_OLLAMA_EMBED_DIM: "1024",
            KEY_OLLAMA_API_KEY: "ollama-cloud-key",
            KEY_OLLAMA_TIMEOUT_SEC: "180",
            KEY_OLLAMA_EMBED_BATCH_SIZE: "4",
        },
    )
    invalidate_settings_cache()
    cfg = get_ollama_runtime_config(db_session, fresh=True)
    assert cfg.base_url == "http://ollama.test:11434"
    assert cfg.embed_model == "bge-m3:latest"
    assert cfg.embed_dim == 1024
    assert cfg.api_key == "ollama-cloud-key"
    assert cfg.timeout_sec == 180.0
    assert cfg.embed_batch_size == 4


def test_ollama_api_key_does_not_fallback_to_env(db_session, monkeypatch):
    invalidate_settings_cache()
    monkeypatch.setenv("OLLAMA_API_KEY", "env-key")
    cfg = get_ollama_runtime_config(db_session, fresh=True)
    assert cfg.api_key is None


def test_db_ollama_base_url_overrides_env(db_session, monkeypatch):
    update_settings(
        db_session,
        {KEY_OLLAMA_BASE_URL: "http://db-only.example:11434"},
    )
    invalidate_settings_cache()
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://env-bound.example:11434")
    cfg = get_ollama_runtime_config(db_session, fresh=True)
    assert cfg.base_url == "http://db-only.example:11434"


def test_env_fallback_when_no_db_rows(db_session, monkeypatch):
    invalidate_settings_cache()
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "custom-embed:latest")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SEC", "240")
    monkeypatch.setenv("OLLAMA_EMBED_BATCH_SIZE", "16")
    cfg = get_ollama_runtime_config(db_session, fresh=True)
    assert cfg.embed_model == "custom-embed:latest"
    assert cfg.timeout_sec == 240.0
    assert cfg.embed_batch_size == 16


def test_db_overrides_env_for_non_base_url_keys(db_session, monkeypatch):
    update_settings(
        db_session,
        {
            KEY_OLLAMA_EMBED_MODEL: "from-db:latest",
            KEY_OLLAMA_TIMEOUT_SEC: "90",
        },
    )
    invalidate_settings_cache()
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", "from-env:latest")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SEC", "600")
    cfg = get_ollama_runtime_config(db_session, fresh=True)
    assert cfg.embed_model == "from-db:latest"
    assert cfg.timeout_sec == 90.0


def test_fresh_false_uses_runtime_cache(db_session):
    from models.system_setting import SystemSetting

    update_settings(db_session, {KEY_OLLAMA_EMBED_MODEL: "v1:latest"})
    invalidate_settings_cache()
    invalidate_ollama_runtime_cache()
    cfg1 = get_ollama_runtime_config(db_session, fresh=True)
    assert cfg1.embed_model == "v1:latest"

    row = (
        db_session.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_OLLAMA_EMBED_MODEL)
        .first()
    )
    assert row is not None
    row.value = "v2:latest"
    db_session.commit()

    cfg_cached = get_ollama_runtime_config(db_session, fresh=False)
    assert cfg_cached.embed_model == "v1:latest"

    cfg_fresh = get_ollama_runtime_config(db_session, fresh=True)
    assert cfg_fresh.embed_model == "v2:latest"


@patch("services.ollama_config_service.httpx.Client")
def test_probe_ollama_ok(mock_client_cls):
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"models": [{"name": "bge-m3:latest"}]}
    client.get.return_value = response
    cfg = OllamaRuntimeConfig(
        base_url="http://127.0.0.1:11434",
        embed_model="bge-m3:latest",
        embed_dim=1024,
        chat_model="qwen2.5:7b",
        timeout_sec=120.0,
        embed_batch_size=8,
        num_parallel=4,
        embed_concurrency=4,
    )
    result = probe_ollama(cfg)
    assert result["ok"] is True
    assert result["model_present"] is True


@patch("services.ollama_config_service.httpx.Client")
def test_probe_ollama_missing_model(mock_client_cls):
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"models": [{"name": "nomic-embed-text"}]}
    client.get.return_value = response
    cfg = OllamaRuntimeConfig(
        base_url="http://127.0.0.1:11434",
        embed_model="bge-m3:latest",
        embed_dim=1024,
        chat_model="qwen2.5:7b",
        timeout_sec=120.0,
        embed_batch_size=8,
        num_parallel=4,
        embed_concurrency=4,
    )
    result = probe_ollama(cfg)
    assert result["ok"] is False
    assert result["errors"]


@patch("services.ollama_config_service.httpx.Client")
def test_probe_ollama_connection_error(mock_client_cls, monkeypatch):
    monkeypatch.delenv("FILEX_ENV", raising=False)
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.get.side_effect = httpx.ConnectError("refused")
    cfg = OllamaRuntimeConfig(
        base_url="http://127.0.0.1:11434",
        embed_model="bge-m3:latest",
        embed_dim=1024,
        chat_model="qwen2.5:7b",
        timeout_sec=120.0,
        embed_batch_size=8,
        num_parallel=4,
        embed_concurrency=4,
    )
    result = probe_ollama(cfg)
    assert result["ok"] is False


@patch("services.ollama_config_service.httpx.Client")
def test_probe_ollama_compose_network_hint(mock_client_cls, monkeypatch):
    monkeypatch.delenv("FILEX_ENV", raising=False)
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.get.side_effect = httpx.ConnectError("name resolution")
    cfg = OllamaRuntimeConfig(
        base_url="http://filex-ollama:11434",
        embed_model="bge-m3:latest",
        embed_dim=1024,
        chat_model="qwen2.5:7b",
        timeout_sec=120.0,
        embed_batch_size=8,
        num_parallel=4,
        embed_concurrency=4,
    )
    result = probe_ollama(cfg)
    assert result["ok"] is False
    assert result["compose_network_hint"]
    assert "filex-ollama" in str(result["compose_network_hint"])


def test_parse_ollama_num_parallel_bounds_and_default():
    assert _parse_ollama_num_parallel("8") == 8
    assert _parse_ollama_num_parallel("0") == 1  # min
    assert _parse_ollama_num_parallel("999") == 32  # max
    assert _parse_ollama_num_parallel("bad") == 4  # default


def test_parse_ollama_embed_concurrency_bounds_and_default():
    assert _parse_ollama_embed_concurrency("6") == 6
    assert _parse_ollama_embed_concurrency("-1") == 1
    assert _parse_ollama_embed_concurrency("100") == 32
    assert _parse_ollama_embed_concurrency("foo") == 4


def test_ollama_num_parallel_and_embed_concurrency_persist_and_runtime(db_session):
    update_settings(
        db_session,
        {
            KEY_OLLAMA_NUM_PARALLEL: "12",
            KEY_OLLAMA_EMBED_CONCURRENCY: "5",
        },
    )
    invalidate_ollama_runtime_cache()
    cfg = get_ollama_runtime_config(db_session, fresh=True)
    assert cfg.num_parallel == 12
    assert cfg.embed_concurrency == 5
