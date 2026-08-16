# Copyright (c) 2026 徐泽宇
"""KB post-processing Chat LLM runtime and client tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy.orm import Session

from services.gpu_model_lifecycle_service import GpuExecutionContext, GpuOomError
from services.system_setting_service import (
    KEY_KB_POST_LLM_API_KEY,
    KEY_KB_POST_LLM_BASE_URL,
    KEY_KB_POST_LLM_JSON_MODE,
    KEY_KB_POST_LLM_MODEL,
    KEY_KB_POST_LLM_PROVIDER,
    invalidate_settings_cache,
    update_settings,
)


def _response(payload: dict, *, status_code: int = 200, raise_error: Exception | None = None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    if raise_error is not None:
        response.raise_for_status.side_effect = raise_error
    return response


def test_runtime_defaults_to_ollama_config(db_session):
    from services.kb_post_llm_service import get_kb_post_llm_runtime_config

    cfg = get_kb_post_llm_runtime_config(db_session, fresh=True)
    assert cfg.provider == "ollama"
    assert cfg.base_url
    assert cfg.model
    assert cfg.api_key is None


def test_chat_model_validates_purpose_specific_output(db_session):
    from pydantic import BaseModel
    from services.kb_post_llm_service import chat_model

    class Output(BaseModel):
        summary: str

    with patch(
        "services.kb_post_llm_service.chat_json",
        return_value={"summary": "typed"},
    ):
        result = chat_model(
            "Return JSON",
            db=db_session,
            purpose="raptor_summary",
            output_type=Output,
        )
    assert result == Output(summary="typed")


def test_chat_model_rejects_invalid_structured_output(db_session):
    from pydantic import BaseModel
    from services.kb_post_llm_service import chat_model

    class Output(BaseModel):
        summary: str

    with patch(
        "services.kb_post_llm_service.chat_json",
        return_value={"summary": 42},
    ):
        result = chat_model(
            "Return JSON",
            db=db_session,
            purpose="raptor_summary",
            output_type=Output,
        )
    assert result is None


@patch("services.kb_post_llm_service.httpx.Client")
def test_ollama_chat_disables_thinking_for_structured_post_processing(mock_client_cls):
    from services.kb_post_llm_service import KbPostLlmRuntimeConfig, _ollama_chat_json

    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.post.return_value = _response(
        {"model": "qwen3.5:9b", "message": {"content": '{"summary": "ok"}'}}
    )
    cfg = KbPostLlmRuntimeConfig(
        provider="ollama",
        base_url="http://filex-ollama:11434",
        model="qwen3.5:9b",
        api_key=None,
        timeout_sec=120.0,
        json_mode="auto",
    )

    parsed = _ollama_chat_json(
        cfg,
        "Return a JSON summary.",
        purpose="raptor_summary",
        timeout_sec=120.0,
    )

    assert parsed == {"summary": "ok"}
    assert client.post.call_args.kwargs["json"]["think"] is False


@patch("services.kb_post_llm_service.httpx.Client")
def test_ollama_chat_records_gpu_after_model_request(mock_client_cls):
    from services.kb_post_llm_service import (
        KbPostLlmRuntimeConfig,
        collect_kb_post_llm_telemetry,
        _ollama_chat_json,
    )

    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.post.side_effect = [
        _response({"modelfile": "FROM /models/blobs/sha256-real"}),
        _response({"model": "qwen3.5:9b", "message": {"content": '{"ok": true}'}}),
    ]
    client.get.return_value = _response({
        "models": [{"name": "qwen3.5:9b", "size_vram": 1024}]
    })
    cfg = KbPostLlmRuntimeConfig(
        provider="ollama",
        base_url="http://filex-ollama:11434",
        model="qwen3.5:9b",
        api_key=None,
        timeout_sec=120.0,
        json_mode="auto",
    )

    with collect_kb_post_llm_telemetry() as calls:
        assert _ollama_chat_json(cfg, "Return JSON", purpose="raptor_summary", timeout_sec=120) == {"ok": True}

    assert calls[0].model == "qwen3.5:9b"
    assert calls[0].gpu_used == "true"
    assert calls[0].gpu_evidence == "ollama_ps_vram"
    assert client.get.call_count == 1


@patch("services.kb_post_llm_service.httpx.Client")
def test_ollama_cloud_chat_uses_ollama_api_key(mock_client_cls):
    from services.kb_post_llm_service import KbPostLlmRuntimeConfig, _ollama_chat_json

    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.post.return_value = _response(
        {"message": {"content": '{"ok": true}'}}
    )
    cfg = KbPostLlmRuntimeConfig(
        provider="ollama",
        base_url="http://filex-ollama:11434",
        model="deepseek-v4-flash:cloud",
        api_key="ollama-cloud-key",
        timeout_sec=120.0,
        json_mode="auto",
    )

    parsed = _ollama_chat_json(
        cfg,
        "Return JSON",
        purpose="entity_extract",
        timeout_sec=120.0,
    )

    assert parsed == {"ok": True}
    assert client.post.call_args.args[0] == "https://ollama.com/api/chat"
    assert client.post.call_args.kwargs["headers"]["Authorization"] == "Bearer ollama-cloud-key"


@patch("services.kb_post_llm_service.httpx.Client")
def test_ollama_chat_oom_with_gpu_context_raises_gpu_oom(mock_client_cls):
    from services.kb_post_llm_service import KbPostLlmRuntimeConfig, _ollama_chat_json

    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    request = httpx.Request("POST", "http://filex-ollama:11434/api/chat")
    response = httpx.Response(500, request=request, text="CUDA out of memory")
    client.post.return_value = _response(
        {},
        raise_error=httpx.HTTPStatusError("server error", request=request, response=response),
    )
    cfg = KbPostLlmRuntimeConfig(
        provider="ollama",
        base_url="http://filex-ollama:11434",
        model="qwen3.5:9b",
        api_key=None,
        timeout_sec=120.0,
        json_mode="auto",
    )

    with pytest.raises(GpuOomError) as excinfo:
        _ollama_chat_json(
            cfg,
            "Return a JSON summary.",
            purpose="raptor_summary",
            timeout_sec=120.0,
            gpu_context=GpuExecutionContext("lease-1", "fence-1", "job-1"),
        )

    assert "out of memory" in str(excinfo.value)
    assert "job-1" in str(excinfo.value)


@patch("services.kb_post_llm_service.httpx.Client")
def test_ollama_chat_oom_without_gpu_context_returns_none(mock_client_cls):
    from services.kb_post_llm_service import KbPostLlmRuntimeConfig, _ollama_chat_json

    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    request = httpx.Request("POST", "http://filex-ollama:11434/api/chat")
    response = httpx.Response(500, request=request, text="CUDA out of memory")
    client.post.return_value = _response(
        {},
        raise_error=httpx.HTTPStatusError("server error", request=request, response=response),
    )
    cfg = KbPostLlmRuntimeConfig(
        provider="ollama",
        base_url="http://filex-ollama:11434",
        model="qwen3.5:9b",
        api_key=None,
        timeout_sec=120.0,
        json_mode="auto",
    )

    assert (
        _ollama_chat_json(
            cfg,
            "Return a JSON summary.",
            purpose="raptor_summary",
            timeout_sec=120.0,
        )
        is None
    )


@patch("services.kb_post_llm_service.httpx.Client")
def test_chat_json_openai_compatible_happy_path(mock_client_cls, db_session):
    from services.kb_post_llm_service import chat_json

    update_settings(
        db_session,
        {
            KEY_KB_POST_LLM_PROVIDER: "openai_compatible",
            KEY_KB_POST_LLM_BASE_URL: "https://llm.example.com/v1",
            KEY_KB_POST_LLM_MODEL: "deepseek-chat",
            KEY_KB_POST_LLM_API_KEY: "sk-openai-compatible",
            KEY_KB_POST_LLM_JSON_MODE: "response_format",
        },
    )
    invalidate_settings_cache()
    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.post.return_value = _response(
        {"choices": [{"message": {"content": '{"ok": true, "items": [1]}'}}]}
    )

    parsed = chat_json("Return JSON", db=db_session, purpose="entity_extract")

    assert parsed == {"ok": True, "items": [1]}
    _, kwargs = client.post.call_args
    assert client.post.call_args.args[0] == "https://llm.example.com/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-openai-compatible"
    assert kwargs["json"]["model"] == "deepseek-chat"
    assert kwargs["json"]["response_format"] == {"type": "json_object"}


@patch("services.kb_post_llm_service.httpx.Client")
def test_chat_json_auto_falls_back_when_response_format_unsupported(mock_client_cls, db_session):
    from services.kb_post_llm_service import chat_json

    update_settings(
        db_session,
        {
            KEY_KB_POST_LLM_PROVIDER: "openai_compatible",
            KEY_KB_POST_LLM_BASE_URL: "https://llm.example.com/v1",
            KEY_KB_POST_LLM_MODEL: "qwen-plus",
            KEY_KB_POST_LLM_JSON_MODE: "auto",
        },
    )
    invalidate_settings_cache()

    request = httpx.Request("POST", "https://llm.example.com/v1/chat/completions")
    first_response = httpx.Response(
        400,
        request=request,
        json={"error": {"message": "response_format is not supported"}},
    )
    first_error = httpx.HTTPStatusError("bad request", request=request, response=first_response)

    client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = client
    client.post.side_effect = [
        _response({}, status_code=400, raise_error=first_error),
        _response({"choices": [{"message": {"content": '{"fallback": true}'}}]}),
    ]

    parsed = chat_json("Return JSON", db=db_session, purpose="sag_event_extract")

    assert parsed == {"fallback": True}
    first_payload = client.post.call_args_list[0].kwargs["json"]
    second_payload = client.post.call_args_list[1].kwargs["json"]
    assert first_payload["response_format"] == {"type": "json_object"}
    assert "response_format" not in second_payload


def test_fresh_runtime_reads_updated_settings_with_new_session(db_session):
    from services.kb_post_llm_service import get_kb_post_llm_runtime_config

    update_settings(
        db_session,
        {
            KEY_KB_POST_LLM_PROVIDER: "openai_compatible",
            KEY_KB_POST_LLM_BASE_URL: "https://llm-a.example.com/v1",
            KEY_KB_POST_LLM_MODEL: "model-a",
        },
    )
    cfg_a = get_kb_post_llm_runtime_config(db_session, fresh=True)
    assert cfg_a.model == "model-a"

    update_settings(db_session, {KEY_KB_POST_LLM_MODEL: "model-b"})
    cfg_fresh_same_session = get_kb_post_llm_runtime_config(db_session, fresh=True)
    assert cfg_fresh_same_session.model == "model-b"

    worker_session = Session(bind=db_session.connection())
    try:
        cfg_fresh_worker = get_kb_post_llm_runtime_config(worker_session, fresh=True)
    finally:
        worker_session.close()
    assert cfg_fresh_worker.model == "model-b"
