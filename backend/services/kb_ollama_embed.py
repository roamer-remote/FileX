# Copyright (c) 2026 徐泽宇
"""Ollama embedding: /api/embed, legacy /api/embeddings, or OpenAI /v1/embeddings.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import concurrent.futures
import logging
from collections.abc import Callable

import httpx

from services.ollama_config_service import OllamaRuntimeConfig, get_ollama_runtime_config

logger = logging.getLogger(__name__)

_EMBED_PATH = "/api/embed"
_EMBEDDINGS_PATH = "/api/embeddings"
_OPENAI_EMBED_PATH = "/v1/embeddings"


class OllamaEmbedError(Exception):
    """Embedding request failed."""


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def _parse_native_vectors(data: object, expected: int) -> list[list[float]]:
    if not isinstance(data, dict):
        raise OllamaEmbedError("invalid embedding response")
    batch = data.get("embeddings")
    if isinstance(batch, list) and len(batch) == expected:
        if all(isinstance(row, list) for row in batch):
            return batch  # type: ignore[return-value]
    one = data.get("embedding")
    if expected == 1 and isinstance(one, list):
        return [one]
    raise OllamaEmbedError("invalid embedding response")


def _parse_openai_vectors(data: object, expected: int) -> list[list[float]]:
    if not isinstance(data, dict):
        raise OllamaEmbedError("invalid OpenAI embedding response")
    rows = data.get("data")
    if not isinstance(rows, list) or len(rows) != expected:
        raise OllamaEmbedError("invalid OpenAI embedding response")
    out: list[list[float]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise OllamaEmbedError("invalid OpenAI embedding response")
        emb = row.get("embedding")
        if not isinstance(emb, list):
            raise OllamaEmbedError("invalid OpenAI embedding response")
        out.append(emb)
    return out


_EMBED_NAME_HINTS = ("embed", "bge", "nomic", "e5", "mxbai")


def _list_ollama_model_names(client: httpx.Client, cfg: OllamaRuntimeConfig) -> list[str]:
    r = client.get(f"{cfg.base_url}/api/tags")
    if r.status_code != 200:
        return []
    return [
        m.get("name", "")
        for m in (r.json().get("models") or [])
        if isinstance(m, dict) and m.get("name")
    ]


def _suggest_embed_models(names: list[str], cfg: OllamaRuntimeConfig) -> str:
    hits = [n for n in names if any(h in n.lower() for h in _EMBED_NAME_HINTS)]
    if not hits:
        return ""
    first = hits[0]
    return (
        f"宿主机已有嵌入模型如 {', '.join(hits[:3])}；"
        f"可设置 ollama_embed_model={first} 与匹配的 ollama_embed_dim（bge-m3 为 1024），"
        f"或执行 ollama pull {cfg.embed_model}"
    )


def _ensure_vector_dims(vectors: list[list[float]], cfg: OllamaRuntimeConfig) -> list[list[float]]:
    from schemas.model_capability_contract import ModelCapabilityContract, RetryPolicy
    from services.model_capability_service import assert_capability, validate_model_response

    contract = ModelCapabilityContract(
        provider="ollama",
        model=cfg.embed_model,
        model_version=cfg.embed_model,
        purpose="embedding",
        input_contract={"required_fields": ["text"], "field_types": {"text": "string"}},
        output_contract={
            "required_fields": ["vector"],
            "field_types": {"vector": "array"},
            "array_item_types": {"vector": "number"},
        },
        embedding_dimension=cfg.embed_dim,
        context_limit=None,
        timeout_seconds=cfg.timeout_sec,
        retry_policy=RetryPolicy(max_retries=0, backoff_seconds=0),
        capabilities=["batch"],
    )
    assert_capability(contract, purpose="embedding", expected_embedding_dimension=cfg.embed_dim)
    for i, vec in enumerate(vectors):
        try:
            validate_model_response(contract, {"vector": vec})
        except Exception as exc:
            raise OllamaEmbedError("malformed embedding response") from exc
        if len(vec) != cfg.embed_dim:
            raise OllamaEmbedError(
                f"Ollama 返回第 {i + 1} 段向量维度 {len(vec)}，"
                f"与 ollama_embed_dim={cfg.embed_dim} 不一致；"
                "请调整系统设置或环境变量并执行 alembic upgrade head 后重新索引。"
            )
    return vectors


def _post_json(client: httpx.Client, cfg: OllamaRuntimeConfig, path: str, payload: dict) -> httpx.Response:
    return client.post(f"{cfg.base_url}{path}", json=payload)


def _ollama_diagnostic(client: httpx.Client, cfg: OllamaRuntimeConfig) -> str:
    """Best-effort probe for operator-facing errors."""
    parts: list[str] = [f"base={cfg.base_url}", f"model={cfg.embed_model}"]
    try:
        r = client.get(f"{cfg.base_url}/api/tags")
        parts.append(f"/api/tags={r.status_code}")
        if r.status_code == 200:
            names = [
                m.get("name", "")
                for m in (r.json().get("models") or [])
                if isinstance(m, dict)
            ]
            want = cfg.embed_model.split(":")[0]
            hit = any(n == cfg.embed_model or n.startswith(want + ":") for n in names)
            parts.append("model_present=" + ("yes" if hit else "no"))
            if not hit and names:
                embed_only = [n for n in names if any(h in n.lower() for h in _EMBED_NAME_HINTS)]
                parts.append(f"embed_models={', '.join(embed_only[:5])}")
                hint = _suggest_embed_models(names, cfg)
                if hint:
                    parts.append(hint)
        else:
            parts.append(r.text[:200])
    except httpx.HTTPError as e:
        parts.append(f"/api/tags_error={e}")
    parts.append(
        "若 /api/tags 非 200，Ollama 地址可能不可达；容器内应使用 http://filex-ollama:11434"
    )
    return "；".join(parts)


def _try_embed_modern(
    client: httpx.Client, texts: list[str], cfg: OllamaRuntimeConfig
) -> tuple[list[list[float]] | None, str | None]:
    payload: dict = {"model": cfg.embed_model, "input": texts[0] if len(texts) == 1 else texts}
    r = _post_json(client, cfg, _EMBED_PATH, payload)
    if r.status_code == 404:
        return None, f"/api/embed=404 body={r.text[:120]!r}"
    try:
        r.raise_for_status()
    except httpx.HTTPError:
        return None, f"/api/embed={r.status_code} body={r.text[:120]!r}"
    return _parse_native_vectors(r.json(), len(texts)), None


def _try_embed_legacy(
    client: httpx.Client, texts: list[str], cfg: OllamaRuntimeConfig
) -> tuple[list[list[float]] | None, str | None]:
    if len(texts) == 1:
        r = _post_json(client, cfg, _EMBEDDINGS_PATH, {"model": cfg.embed_model, "prompt": texts[0]})
        if r.status_code == 404:
            return None, f"/api/embeddings=404 body={r.text[:120]!r}"
        try:
            r.raise_for_status()
            return _parse_native_vectors(r.json(), 1), None
        except httpx.HTTPError:
            return None, f"/api/embeddings={r.status_code} body={r.text[:120]!r}"

    r = _post_json(client, cfg, _EMBEDDINGS_PATH, {"model": cfg.embed_model, "input": texts})
    if r.status_code == 200:
        try:
            return _parse_native_vectors(r.json(), len(texts)), None
        except OllamaEmbedError:
            pass

    notes: list[str] = []
    out: list[list[float]] = []
    for t in texts:
        r = _post_json(client, cfg, _EMBEDDINGS_PATH, {"model": cfg.embed_model, "prompt": t})
        if r.status_code == 404:
            return None, "/api/embeddings=404 (batch fallback)"
        try:
            r.raise_for_status()
            out.extend(_parse_native_vectors(r.json(), 1))
        except httpx.HTTPError:
            notes.append(f"prompt={r.status_code}")
    if len(out) == len(texts):
        return out, None
    return None, ";".join(notes) if notes else "legacy batch failed"


def _try_embed_openai(
    client: httpx.Client, texts: list[str], cfg: OllamaRuntimeConfig
) -> tuple[list[list[float]] | None, str | None]:
    payload = {
        "model": cfg.embed_model,
        "input": texts[0] if len(texts) == 1 else texts,
    }
    r = _post_json(client, cfg, _OPENAI_EMBED_PATH, payload)
    if r.status_code == 404:
        return None, f"/v1/embeddings=404 body={r.text[:120]!r}"
    try:
        r.raise_for_status()
    except httpx.HTTPError:
        return None, f"/v1/embeddings={r.status_code} body={r.text[:120]!r}"
    return _parse_openai_vectors(r.json(), len(texts)), None


def log_ollama_startup() -> None:
    """Log Ollama reachability at worker startup (non-fatal)."""
    cfg = get_ollama_runtime_config(fresh=True)
    try:
        with httpx.Client(timeout=min(cfg.timeout_sec, 15.0)) as client:
            logger.info("Ollama startup probe: %s", _ollama_diagnostic(client, cfg))
    except httpx.HTTPError as e:
        logger.warning("Ollama startup probe failed: %s", e)


def _embed_texts_once(client: httpx.Client, texts: list[str], cfg: OllamaRuntimeConfig) -> list[list[float]]:
    """对一批文本调用 Ollama（条数应 ≤ ollama_embed_batch_size）。"""
    attempts: list[str] = []
    for try_fn in (_try_embed_modern, _try_embed_legacy, _try_embed_openai):
        vectors, note = try_fn(client, texts, cfg)
        if note:
            attempts.append(note)
        if vectors is not None:
            return _ensure_vector_dims(vectors, cfg)
    diag = _ollama_diagnostic(client, cfg)
    names = _list_ollama_model_names(client, cfg)
    extra = _suggest_embed_models(names, cfg)
    raise OllamaEmbedError(
        "Ollama 嵌入全部失败（"
        + " | ".join(attempts)
        + "）。"
        + diag
        + (f"。{extra}" if extra else f"。请执行: ollama pull {cfg.embed_model}")
    )


def _emit_chunk_progress(
    progress_cb: Callable[[int, int], None] | None,
    *,
    batch_start: int,
    batch_len: int,
    total: int,
) -> None:
    """Notify progress after a batch completes (1-based chunk index, total count)."""
    if progress_cb is None:
        return
    for offset in range(batch_len):
        progress_cb(batch_start + offset + 1, total)


def embed_texts(
    texts: list[str],
    *,
    heartbeat_cb: Callable[[], None] | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    cfg = get_ollama_runtime_config(fresh=True)
    batch_size = cfg.embed_batch_size
    concurrency = max(1, int(cfg.embed_concurrency))
    timeout = httpx.Timeout(cfg.timeout_sec)

    # 切分批次（保留顺序）
    batches: list[list[str]] = []
    for start in range(0, len(texts), batch_size):
        batches.append(texts[start : start + batch_size])

    batch_starts: list[int] = []
    pos = 0
    for batch in batches:
        batch_starts.append(pos)
        pos += len(batch)

    out: list[list[float]] = [[] for _ in batches]  # 占位，按索引回填

    def _embed_one_batch(idx: int, batch: list[str]) -> list[list[float]]:
        """单批嵌入（独立 Client，避免 httpx 线程共享问题）。"""
        try:
            with httpx.Client(timeout=timeout) as client:
                vecs = _embed_texts_once(client, batch, cfg)
        except httpx.TimeoutException as exc:
            raise OllamaEmbedError(
                f"Ollama 嵌入请求超时（{cfg.timeout_sec}s），"
                f"本批 {len(batch)} 段、全文共 {len(texts)} 段；"
                f"可增大 ollama_timeout_sec 或减小 ollama_embed_batch_size（当前 {batch_size}），"
                f"并确认 Ollama 可达：{cfg.base_url}"
            ) from exc
        if heartbeat_cb is not None:
            heartbeat_cb()
        return vecs

    if concurrency <= 1 or len(batches) <= 1:
        # 串行路径（兼容低并发或极小文档；也便于测试精确断言）
        for i, b in enumerate(batches):
            out[i] = _embed_one_batch(i, b)
            _emit_chunk_progress(
                progress_cb,
                batch_start=batch_starts[i],
                batch_len=len(b),
                total=len(texts),
            )
    else:
        # 并发路径：
        # - 使用 as_completed + fut.result() 实现 fail-fast（首个失败立即抛出，与串行行为一致）
        # - 正在执行的其他 batch 可能继续直至自然结束或 GC（非严格 cancel）。
        # - 如需更激进取消（Py 3.9+）：ex.shutdown(wait=False, cancel_futures=True)
        # 记录为已知行为；当前与规格“快速失败”意图匹配。
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            future_to_idx = {ex.submit(_embed_one_batch, i, b): i for i, b in enumerate(batches)}
            for fut in concurrent.futures.as_completed(future_to_idx):
                i = future_to_idx[fut]
                out[i] = fut.result()
                _emit_chunk_progress(
                    progress_cb,
                    batch_start=batch_starts[i],
                    batch_len=len(batches[i]),
                    total=len(texts),
                )

    # 展平并最终校验
    final: list[list[float]] = []
    for vecs in out:
        final.extend(vecs)

    if len(final) != len(texts):
        raise OllamaEmbedError(f"嵌入条数 {len(final)} 与文本段数 {len(texts)} 不一致")

    if len(batches) > 1:
        logger.info(
            "embed_texts concurrency=%d batch_size=%d chunks=%d (effective concurrency path)",
            concurrency, batch_size, len(texts)
        )
    return final
