# Copyright (c) 2026 徐泽宇
"""Shared Chat LLM client for KB post-processing phases."""

from __future__ import annotations

import json
import logging
import threading
import time
from urllib.parse import quote
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from models.system_setting import SystemSetting
from services.ollama_config_service import get_ollama_runtime_config
from services.system_setting_service import (
    KEY_KB_POST_LLM_API_KEY,
    KEY_KB_POST_LLM_BASE_URL,
    KEY_KB_POST_LLM_JSON_MODE,
    KEY_KB_POST_LLM_MODEL,
    KEY_KB_POST_LLM_PROVIDER,
    KEY_KB_POST_LLM_TIMEOUT_SEC,
    get_fresh_public_settings_dict,
    get_public_settings_dict,
    secret_credential_from_stored,
)
from services.gpu_model_lifecycle_service import (
    GpuExecutionContext,
    GpuOomError,
    is_gpu_oom_error,
)

logger = logging.getLogger(__name__)

KbPostLlmProvider = Literal["ollama", "openai_compatible"]
KbPostLlmJsonMode = Literal["auto", "response_format", "prompt_only"]
KbPostLlmPurpose = Literal[
    "entity_extract",
    "sag_event_extract",
    "raptor_summary",
    "query_understand",
    "fulltext_reason",
]


@dataclass(frozen=True)
class KbPostLlmCallTelemetry:
    purpose: str
    provider: str
    model: str
    model_path: str | None
    gpu_used: str
    gpu_evidence: str
    model_path_scope: str
    model_path_resolved: bool


_telemetry_calls: ContextVar[list[KbPostLlmCallTelemetry] | None] = ContextVar(
    "kb_post_llm_telemetry_calls", default=None
)


@contextmanager
def collect_kb_post_llm_telemetry(calls: list[KbPostLlmCallTelemetry] | None = None):
    calls = calls if calls is not None else []
    token = _telemetry_calls.set(calls)
    try:
        yield calls
    finally:
        _telemetry_calls.reset(token)


def record_kb_post_llm_call(
    *,
    purpose: str,
    provider: str,
    model: str,
    model_path: str | None,
    model_path_scope: str = "unknown",
    model_path_resolved: bool = False,
    gpu_context: GpuExecutionContext | None,
    gpu_used: str = "unknown",
    gpu_evidence: str = "unavailable",
) -> None:
    calls = _telemetry_calls.get()
    if calls is not None:
        call = KbPostLlmCallTelemetry(
            purpose=purpose,
            provider=provider,
            model=model,
            model_path=model_path,
            gpu_used=gpu_used,
            gpu_evidence=gpu_evidence,
            model_path_scope=model_path_scope,
            model_path_resolved=model_path_resolved,
        )
        if call not in calls:
            calls.append(call)


def format_kb_post_llm_telemetry(
    calls: list[KbPostLlmCallTelemetry],
) -> dict[str, object]:
    if not calls:
        return {}
    unique = list(dict.fromkeys(calls))
    def encode(values: list[str]) -> str:
        # operation_logs.detail is a whitespace-delimited key=value format;
        # encode values so absolute paths and model names remain one field.
        return ",".join(quote(value, safe="") for value in values)

    return {
        "llm_purposes": encode([call.purpose for call in unique]),
        "llm_providers": encode([call.provider for call in unique]),
        "llm_models": encode([call.model for call in unique]),
        "llm_model_paths": encode([call.model_path or "unknown" for call in unique]),
        "llm_model_path_scopes": encode([call.model_path_scope for call in unique]),
        "llm_model_path_resolved": encode([
            str(call.model_path_resolved).lower() for call in unique
        ]),
        "llm_gpu_used": encode([call.gpu_used for call in unique]),
        "llm_gpu_evidence": encode([call.gpu_evidence for call in unique]),
    }


def _ollama_model_path_from_show(body: dict[str, Any]) -> str | None:
    """Return all absolute model-file paths exposed by Ollama's metadata."""
    modelfile = str(body.get("modelfile") or "")
    paths = [
        line.strip()[5:].strip()
        for line in modelfile.splitlines()
        if line.strip().upper().startswith("FROM ")
        and line.strip()[5:].strip().startswith("/")
    ]
    if not paths:
        return None
    return "|".join(dict.fromkeys(paths))


def _ollama_gpu_usage(client: httpx.Client, base_url: str, model: str) -> tuple[str, str]:
    try:
        response = client.get(f"{base_url}/api/ps")
        response.raise_for_status()
        models = response.json().get("models") or []
        row = next((item for item in models if item.get("name") == model), None)
        if row is None:
            return "unknown", "ollama_ps_model_not_listed"
        return (
            ("true", "ollama_ps_vram")
            if int(row.get("size_vram") or 0) > 0
            else ("false", "ollama_ps_no_vram")
        )
    except Exception:
        return "unknown", "ollama_ps_unavailable"
OutputModelT = TypeVar("OutputModelT", bound=BaseModel)

_runtime_cache: KbPostLlmRuntimeConfig | None = None
_cache_lock = threading.Lock()


def _raise_gpu_oom_if_scheduled(exc: Exception, gpu_context: GpuExecutionContext | None) -> None:
    """GPU 调度执行中遇到显存不足必须上抛给 scheduler，不能吞成 http_error。"""
    if gpu_context is not None and is_gpu_oom_error(exc):
        detail = str(exc)
        response = getattr(exc, "response", None)
        if response is not None:
            try:
                body = str(getattr(response, "text", "") or "")
                if body:
                    detail = f"{detail} body={body[:300]}"
            except Exception:
                pass
        raise GpuOomError(
            f"gpu chat oom lease={gpu_context.gpu_lease_id} job={gpu_context.job_id} error={detail}"
        ) from exc


@dataclass(frozen=True)
class KbPostLlmRuntimeConfig:
    provider: KbPostLlmProvider
    base_url: str
    model: str
    api_key: str | None
    timeout_sec: float
    json_mode: KbPostLlmJsonMode


def invalidate_kb_post_llm_runtime_cache() -> None:
    global _runtime_cache
    with _cache_lock:
        _runtime_cache = None


def _parse_provider(raw: object) -> KbPostLlmProvider:
    value = str(raw or "ollama").strip().lower()
    return "openai_compatible" if value == "openai_compatible" else "ollama"


def _parse_json_mode(raw: object) -> KbPostLlmJsonMode:
    value = str(raw or "auto").strip().lower()
    if value in {"response_format", "prompt_only"}:
        return value  # type: ignore[return-value]
    return "auto"


def _parse_timeout(raw: object) -> float:
    try:
        return max(5.0, min(300.0, float(str(raw).strip())))
    except ValueError:
        return 60.0


def _runtime_from_settings(db: Session, *, fresh: bool) -> KbPostLlmRuntimeConfig:
    settings = get_fresh_public_settings_dict(db) if fresh else get_public_settings_dict(db)
    provider = _parse_provider(settings.get(KEY_KB_POST_LLM_PROVIDER))
    if provider == "ollama":
        ollama = get_ollama_runtime_config(db, fresh=True)
        return KbPostLlmRuntimeConfig(
            provider="ollama",
            base_url=ollama.base_url.rstrip("/"),
            model=ollama.chat_model,
            api_key=ollama.api_key,
            timeout_sec=ollama.timeout_sec,
            json_mode="auto",
        )
    api_key_row = (
        db.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_KB_POST_LLM_API_KEY)
        .first()
    )
    api_key = secret_credential_from_stored(api_key_row.value if api_key_row else "")
    return KbPostLlmRuntimeConfig(
        provider="openai_compatible",
        base_url=str(settings.get(KEY_KB_POST_LLM_BASE_URL) or "").strip().rstrip("/"),
        model=str(settings.get(KEY_KB_POST_LLM_MODEL) or "").strip(),
        api_key=api_key or None,
        timeout_sec=_parse_timeout(settings.get(KEY_KB_POST_LLM_TIMEOUT_SEC)),
        json_mode=_parse_json_mode(settings.get(KEY_KB_POST_LLM_JSON_MODE)),
    )


def get_kb_post_llm_runtime_config(
    db: Session | None = None, *, fresh: bool = False
) -> KbPostLlmRuntimeConfig:
    global _runtime_cache

    if not fresh:
        with _cache_lock:
            if _runtime_cache is not None:
                return _runtime_cache

    if db is None:
        from database import SessionLocal

        db = SessionLocal()
        try:
            loaded = _runtime_from_settings(db, fresh=True)
        finally:
            db.close()
    else:
        loaded = _runtime_from_settings(db, fresh=fresh)

    with _cache_lock:
        _runtime_cache = loaded
    return loaded


def _content_from_response(provider: KbPostLlmProvider, body: dict[str, Any]) -> str | None:
    if provider == "ollama":
        content = (body.get("message") or {}).get("content")
    else:
        choices = body.get("choices") or []
        first = choices[0] if choices and isinstance(choices[0], dict) else {}
        content = (first.get("message") or {}).get("content")
    return str(content) if content else None


def _parse_json_content(content: str | None, *, purpose: KbPostLlmPurpose) -> dict[str, Any] | None:
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("kb_post_llm invalid json purpose=%s", purpose)
        return None
    return parsed if isinstance(parsed, dict) else None


def _openai_response_format_unsupported(exc: httpx.HTTPStatusError) -> bool:
    if exc.response.status_code not in (400, 422):
        return False
    try:
        text = exc.response.text.lower()
    except Exception:
        text = ""
    return "response_format" in text


def _ollama_chat_json(
    cfg: KbPostLlmRuntimeConfig,
    prompt: str,
    *,
    purpose: KbPostLlmPurpose,
    timeout_sec: float | None,
    gpu_context: GpuExecutionContext | None = None,
) -> dict[str, Any] | None:
    payload = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        # qwen3.5 enables thinking by default; structured post-processing
        # needs the JSON answer directly and should not spend the timeout
        # budget emitting an unbounded reasoning trace.
        "think": False,
    }
    chat_url = f"{cfg.base_url}/api/chat"
    headers: dict[str, str] | None = None
    if cfg.model.endswith(":cloud") and cfg.api_key:
        chat_url = "https://ollama.com/api/chat"
        headers = {"Authorization": f"Bearer {cfg.api_key}"}
    if gpu_context is not None:
        headers = dict(headers or {})
        headers.update(
            {
                "X-FileX-GPU-Lease-ID": gpu_context.gpu_lease_id,
                "X-FileX-Fencing-Token": gpu_context.fencing_token,
                "X-FileX-GPU-Job-ID": gpu_context.job_id,
            }
        )
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=max(5.0, float(timeout_sec or cfg.timeout_sec))) as client:
            model_path: str | None = None
            model_path_scope = "remote" if cfg.model.endswith(":cloud") else "unknown"
            model_path_resolved = False
            telemetry_enabled = _telemetry_calls.get() is not None
            gpu_used, gpu_evidence = (
                ("unknown", "remote_provider")
                if cfg.model.endswith(":cloud")
                else ("unknown", "ollama_ps_not_checked")
            )
            if telemetry_enabled and not cfg.model.endswith(":cloud"):
                try:
                    show = client.post(f"{cfg.base_url}/api/show", json={"name": cfg.model})
                    show.raise_for_status()
                    model_path = _ollama_model_path_from_show(show.json())
                    model_path_scope = "container" if model_path else "unknown"
                    model_path_resolved = bool(model_path)
                except Exception:
                    logger.debug("kb_post_llm model path probe failed model=%s", cfg.model, exc_info=True)
            response = client.post(chat_url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
            if telemetry_enabled and not cfg.model.endswith(":cloud"):
                # Probe after /api/chat: before the request Ollama may not have
                # loaded the model yet, which would falsely report unknown.
                gpu_used, gpu_evidence = _ollama_gpu_usage(
                    client, cfg.base_url, str(body.get("model") or cfg.model)
                )
            if telemetry_enabled:
                record_kb_post_llm_call(
                    purpose=purpose,
                    provider=cfg.provider,
                    model=str(body.get("model") or cfg.model),
                    model_path=model_path,
                    model_path_scope=model_path_scope,
                    model_path_resolved=model_path_resolved,
                    gpu_context=gpu_context,
                    gpu_used=gpu_used,
                    gpu_evidence=gpu_evidence,
                )
    except httpx.TimeoutException:
        logger.warning(
            "kb_post_llm chat failed purpose=%s provider=%s model=%s reason=timeout",
            purpose,
            cfg.provider,
            cfg.model,
        )
        return None
    except Exception as exc:
        _raise_gpu_oom_if_scheduled(exc, gpu_context)
        logger.warning(
            "kb_post_llm chat failed purpose=%s provider=%s model=%s reason=http_error error=%s",
            purpose,
            cfg.provider,
            cfg.model,
            exc,
        )
        return None
    parsed = _parse_json_content(_content_from_response("ollama", body), purpose=purpose)
    logger.info(
        "kb_post_llm chat_done purpose=%s provider=%s model=%s ms=%s ok=%s",
        purpose,
        cfg.provider,
        cfg.model,
        int((time.perf_counter() - started) * 1000),
        parsed is not None,
    )
    return parsed


def _openai_payload(
    cfg: KbPostLlmRuntimeConfig, prompt: str, *, include_response_format: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    if include_response_format:
        payload["response_format"] = {"type": "json_object"}
    return payload


def _openai_chat_json(
    cfg: KbPostLlmRuntimeConfig,
    prompt: str,
    *,
    purpose: KbPostLlmPurpose,
    timeout_sec: float | None,
    gpu_context: GpuExecutionContext | None = None,
) -> dict[str, Any] | None:
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    if gpu_context is not None:
        headers.update(
            {
                "X-FileX-GPU-Lease-ID": gpu_context.gpu_lease_id,
                "X-FileX-Fencing-Token": gpu_context.fencing_token,
                "X-FileX-GPU-Job-ID": gpu_context.job_id,
            }
        )
    include_response_format = cfg.json_mode in ("auto", "response_format")
    attempts = [include_response_format]
    if cfg.json_mode == "auto":
        attempts.append(False)
    started = time.perf_counter()
    last_error: Exception | None = None
    record_kb_post_llm_call(
        purpose=purpose,
        provider=cfg.provider,
        model=cfg.model,
        model_path=None,
        model_path_scope="remote",
        model_path_resolved=False,
        gpu_context=gpu_context,
        gpu_used="unknown",
        gpu_evidence="remote_provider",
    )
    with httpx.Client(timeout=max(5.0, float(timeout_sec or cfg.timeout_sec))) as client:
        for idx, use_response_format in enumerate(attempts):
            try:
                response = client.post(
                    f"{cfg.base_url}/chat/completions",
                    headers=headers,
                    json=_openai_payload(
                        cfg, prompt, include_response_format=use_response_format
                    ),
                )
                response.raise_for_status()
                parsed = _parse_json_content(
                    _content_from_response("openai_compatible", response.json()),
                    purpose=purpose,
                )
                logger.info(
                    "kb_post_llm chat_done purpose=%s provider=%s model=%s ms=%s ok=%s",
                    purpose,
                    cfg.provider,
                    cfg.model,
                    int((time.perf_counter() - started) * 1000),
                    parsed is not None,
                )
                return parsed
            except httpx.HTTPStatusError as exc:
                _raise_gpu_oom_if_scheduled(exc, gpu_context)
                last_error = exc
                if (
                    cfg.json_mode == "auto"
                    and idx == 0
                    and use_response_format
                    and _openai_response_format_unsupported(exc)
                ):
                    logger.warning(
                        "kb_post_llm response_format unsupported purpose=%s provider=%s model=%s",
                        purpose,
                        cfg.provider,
                        cfg.model,
                    )
                    continue
                break
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "kb_post_llm chat failed purpose=%s provider=%s model=%s reason=timeout",
                    purpose,
                    cfg.provider,
                    cfg.model,
                )
                break
            except Exception as exc:
                _raise_gpu_oom_if_scheduled(exc, gpu_context)
                last_error = exc
                break
    logger.warning(
        "kb_post_llm chat failed purpose=%s provider=%s model=%s reason=http_error error=%s",
        purpose,
        cfg.provider,
        cfg.model,
        last_error,
    )
    return None


def chat_json(
    prompt: str,
    *,
    db: Session | None = None,
    purpose: KbPostLlmPurpose,
    timeout_sec: float | None = None,
    fresh: bool = True,
    gpu_context: GpuExecutionContext | None = None,
) -> dict[str, Any] | None:
    cfg = get_kb_post_llm_runtime_config(db, fresh=fresh)
    if cfg.provider == "ollama":
        return _ollama_chat_json(
            cfg, prompt, purpose=purpose, timeout_sec=timeout_sec, gpu_context=gpu_context
        )
    return _openai_chat_json(
        cfg, prompt, purpose=purpose, timeout_sec=timeout_sec, gpu_context=gpu_context
    )


def chat_model(
    prompt: str,
    *,
    output_type: type[OutputModelT],
    db: Session | None = None,
    purpose: KbPostLlmPurpose,
    timeout_sec: float | None = None,
    fresh: bool = True,
    gpu_context: GpuExecutionContext | None = None,
) -> OutputModelT | None:
    """Call the provider and validate the response at the LLM boundary."""
    raw = chat_json(
        prompt,
        db=db,
        purpose=purpose,
        timeout_sec=timeout_sec,
        fresh=fresh,
        gpu_context=gpu_context,
    )
    if raw is None:
        return None
    try:
        return output_type.model_validate(raw)
    except ValidationError as exc:
        logger.warning(
            "kb_post_llm invalid structured output purpose=%s model=%s errors=%s",
            purpose,
            output_type.__name__,
            exc.error_count(),
        )
        return None
