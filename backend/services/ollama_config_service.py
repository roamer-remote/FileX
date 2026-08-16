# Copyright (c) 2026 徐泽宇
"""Ollama runtime configuration from system_settings with env fallback (069)."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from config import (
    OLLAMA_BASE_URL,
    OLLAMA_CHAT_MODEL,
    OLLAMA_EMBED_BATCH_SIZE,
    OLLAMA_EMBED_CONCURRENCY,
    OLLAMA_EMBED_DIM,
    OLLAMA_EMBED_MODEL,
    OLLAMA_NUM_PARALLEL,
    OLLAMA_TIMEOUT_SEC,
)
from services.system_setting_service import (
    KEY_OLLAMA_API_KEY,
    KEY_OLLAMA_BASE_URL,
    KEY_OLLAMA_CHAT_MODEL,
    KEY_OLLAMA_EMBED_BATCH_SIZE,
    KEY_OLLAMA_EMBED_CONCURRENCY,
    KEY_OLLAMA_EMBED_DIM,
    KEY_OLLAMA_EMBED_MODEL,
    KEY_OLLAMA_NUM_PARALLEL,
    KEY_OLLAMA_TIMEOUT_SEC,
    secret_credential_from_stored,
)

_OLLAMA_DB_KEYS = (
    KEY_OLLAMA_BASE_URL,
    KEY_OLLAMA_EMBED_MODEL,
    KEY_OLLAMA_EMBED_DIM,
    KEY_OLLAMA_CHAT_MODEL,
    KEY_OLLAMA_TIMEOUT_SEC,
    KEY_OLLAMA_EMBED_BATCH_SIZE,
    KEY_OLLAMA_NUM_PARALLEL,
    KEY_OLLAMA_EMBED_CONCURRENCY,
    KEY_OLLAMA_API_KEY,
)

_PROBE_TIMEOUT_SEC = 30.0

_ollama_runtime_cache: OllamaRuntimeConfig | None = None
_ollama_cache_lock = threading.Lock()


def invalidate_ollama_runtime_cache() -> None:
    global _ollama_runtime_cache
    with _ollama_cache_lock:
        _ollama_runtime_cache = None


@dataclass(frozen=True)
class OllamaRuntimeConfig:
    base_url: str
    embed_model: str
    embed_dim: int
    chat_model: str
    timeout_sec: float
    embed_batch_size: int
    # 服务端并行度（OLLAMA_NUM_PARALLEL），由 filex-ollama 容器自身消费；客户端不直接使用此值
    num_parallel: int = 4
    embed_concurrency: int = 4
    api_key: str | None = None


def _load_ollama_db_values(db: Session) -> dict[str, str]:
    from models.system_setting import SystemSetting

    rows = (
        db.query(SystemSetting)
        .filter(SystemSetting.setting_key.in_(_OLLAMA_DB_KEYS))
        .all()
    )
    out: dict[str, str] = {}
    for row in rows:
        if row.value is not None and str(row.value).strip():
            out[row.setting_key] = str(row.value).strip()
    return out


def _resolve_str(db_values: dict[str, str], key: str, env_name: str, default: str) -> str:
    """DB non-empty > env > config default (FR-069-002)."""
    if key in db_values:
        return db_values[key]
    env_val = os.environ.get(env_name)
    if env_val is not None and str(env_val).strip():
        return str(env_val).strip()
    return default


def _parse_runtime_from_map(db_values: dict[str, str]) -> OllamaRuntimeConfig:
    base_url = _resolve_str(
        db_values, KEY_OLLAMA_BASE_URL, "OLLAMA_BASE_URL", OLLAMA_BASE_URL
    ).rstrip("/")

    embed_model = _resolve_str(
        db_values, KEY_OLLAMA_EMBED_MODEL, "OLLAMA_EMBED_MODEL", OLLAMA_EMBED_MODEL
    )
    chat_model = _resolve_str(
        db_values, KEY_OLLAMA_CHAT_MODEL, "OLLAMA_CHAT_MODEL", OLLAMA_CHAT_MODEL
    )
    try:
        embed_dim = int(
            _resolve_str(
                db_values, KEY_OLLAMA_EMBED_DIM, "OLLAMA_EMBED_DIM", str(OLLAMA_EMBED_DIM)
            )
        )
    except ValueError:
        embed_dim = OLLAMA_EMBED_DIM
    try:
        timeout_sec = float(
            _resolve_str(
                db_values,
                KEY_OLLAMA_TIMEOUT_SEC,
                "OLLAMA_TIMEOUT_SEC",
                str(OLLAMA_TIMEOUT_SEC),
            )
        )
    except ValueError:
        timeout_sec = OLLAMA_TIMEOUT_SEC
    try:
        embed_batch_size = int(
            _resolve_str(
                db_values,
                KEY_OLLAMA_EMBED_BATCH_SIZE,
                "OLLAMA_EMBED_BATCH_SIZE",
                str(OLLAMA_EMBED_BATCH_SIZE),
            )
        )
    except ValueError:
        embed_batch_size = OLLAMA_EMBED_BATCH_SIZE

    try:
        num_parallel = int(
            _resolve_str(
                db_values,
                KEY_OLLAMA_NUM_PARALLEL,
                "OLLAMA_NUM_PARALLEL",
                str(OLLAMA_NUM_PARALLEL),
            )
        )
    except ValueError:
        num_parallel = OLLAMA_NUM_PARALLEL
    try:
        embed_concurrency = int(
            _resolve_str(
                db_values,
                KEY_OLLAMA_EMBED_CONCURRENCY,
                "OLLAMA_EMBED_CONCURRENCY",
                str(OLLAMA_EMBED_CONCURRENCY),
            )
        )
    except ValueError:
        embed_concurrency = OLLAMA_EMBED_CONCURRENCY
    api_key = secret_credential_from_stored(db_values.get(KEY_OLLAMA_API_KEY, ""))

    return OllamaRuntimeConfig(
        base_url=base_url,
        embed_model=embed_model,
        embed_dim=embed_dim,
        chat_model=chat_model,
        timeout_sec=timeout_sec,
        embed_batch_size=max(1, embed_batch_size),
        num_parallel=max(1, num_parallel),
        embed_concurrency=max(1, embed_concurrency),
        api_key=api_key or None,
    )


def _load_config_from_db(db: Session) -> OllamaRuntimeConfig:
    return _parse_runtime_from_map(_load_ollama_db_values(db))


def get_ollama_runtime_config(db: Session | None = None, *, fresh: bool = False) -> OllamaRuntimeConfig:
    """Load Ollama settings: DB non-empty > env > config default (FR-069-002).

    fresh=False (default): return in-process cached config after first DB load.
    fresh=True: bypass cache, reload from DB, then refresh cache.
    """
    global _ollama_runtime_cache

    if not fresh:
        with _ollama_cache_lock:
            if _ollama_runtime_cache is not None:
                return _ollama_runtime_cache

    if db is None:
        from database import SessionLocal

        db = SessionLocal()
        try:
            loaded = _load_config_from_db(db)
        finally:
            db.close()
    else:
        loaded = _load_config_from_db(db)

    with _ollama_cache_lock:
        _ollama_runtime_cache = loaded
    return loaded


def validate_ollama_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("ollama_base_url 必须为 http/https 且包含 host")
    return normalized


def _probe_urls_for_config(base_url: str) -> list[str]:
    """Configured base URL only (API runs in Compose alongside Ollama)."""
    return [base_url.rstrip("/")]


def _probe_single_url(
    client: httpx.Client, base_url: str, embed_model: str
) -> tuple[int | None, list[str], bool, list[str]]:
    """Returns (tags_status, model_names, model_present, errors)."""
    errors: list[str] = []
    tags_status: int | None = None
    model_names: list[str] = []
    model_present = False
    r = client.get(f"{base_url}/api/tags")
    tags_status = r.status_code
    if r.status_code == 200:
        model_names = [
            m.get("name", "")
            for m in (r.json().get("models") or [])
            if isinstance(m, dict) and m.get("name")
        ]
        want = embed_model.split(":")[0]
        model_present = any(
            n == embed_model or n.startswith(want + ":") for n in model_names
        )
        if not model_present:
            errors.append(f"嵌入模型 {embed_model!r} 未在 Ollama 中找到")
    else:
        errors.append(f"/api/tags 返回 {r.status_code}")
    return tags_status, model_names, model_present, errors


def probe_ollama(config: OllamaRuntimeConfig | None = None) -> dict[str, object]:
    """Best-effort connectivity probe for admin test endpoint."""
    cfg = config or get_ollama_runtime_config(fresh=True)
    urls = _probe_urls_for_config(cfg.base_url)
    errors: list[str] = []
    tags_status: int | None = None
    model_present = False
    model_names: list[str] = []
    probed_url: str | None = None
    last_http_error: httpx.HTTPError | None = None

    try:
        with httpx.Client(timeout=min(cfg.timeout_sec, _PROBE_TIMEOUT_SEC)) as client:
            for url in urls:
                try:
                    tags_status, model_names, model_present, url_errors = _probe_single_url(
                        client, url, cfg.embed_model
                    )
                    probed_url = url
                    errors = url_errors
                    if tags_status == 200 and not url_errors:
                        break
                    if tags_status == 200 and url_errors:
                        break
                except httpx.HTTPError as exc:
                    last_http_error = exc
                    errors = [f"连接 {url} 失败: {exc}"]
                    continue
    except httpx.HTTPError as exc:
        last_http_error = exc
        errors = [f"连接失败: {exc}"]

    if last_http_error and probed_url is None:
        errors = [f"连接失败: {last_http_error}"]

    ok = probed_url is not None and tags_status == 200 and not errors
    compose_network_hint = _compose_network_probe_hint(
        cfg.base_url, errors, tags_status=tags_status, probed_url=probed_url
    )
    message = "Ollama 连通且嵌入模型已就绪" if ok else "Ollama 配置或连通性有问题"
    if compose_network_hint:
        message = f"{message}。{compose_network_hint}"
    return {
        "ok": ok,
        "base_url": cfg.base_url,
        "probed_url": probed_url,
        "embed_model": cfg.embed_model,
        "tags_status": tags_status,
        "model_present": model_present,
        "models": model_names[:10],
        "errors": errors,
        "compose_network_hint": compose_network_hint,
        "message": message,
    }


def _compose_network_probe_hint(
    base_url: str,
    errors: list[str],
    *,
    tags_status: int | None = None,
    probed_url: str | None = None,
) -> str | None:
    """Hint when API runs outside Compose but ollama_base_url targets in-network DNS."""
    if probed_url and probed_url.rstrip("/") != base_url.rstrip("/"):
        return None
    host = (urlparse(base_url.rstrip("/")).hostname or "").lower()
    if host != "filex-ollama":
        return None
    if not any(e.startswith("连接") for e in errors):
        if tags_status and tags_status != 200:
            return (
                "请确认 filex-ollama 容器已运行且同 Compose 网络；"
                "ollama_base_url 应为 http://filex-ollama:11434。"
            )
        return None
    return (
        "请确认 filex-ollama 容器已运行（./start.sh 或 compose up）；"
        "API 须在 filex 等 Compose 容器内经 http://filex-ollama:11434 访问 Ollama。"
    )
