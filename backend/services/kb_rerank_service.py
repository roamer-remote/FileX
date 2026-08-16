# Copyright (c) 2026 徐泽宇
"""Optional cross-encoder rerank via HTTP (TEI / generic JSON APIs).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

KB_RERANK_URL = (os.environ.get("KB_RERANK_URL") or "").strip().rstrip("/")
KB_RERANK_TIMEOUT_SEC = float(os.environ.get("KB_RERANK_TIMEOUT_SEC") or "30")
KB_RERANK_API_KEY = (os.environ.get("KB_RERANK_API_KEY") or "").strip()
# TEI text-embeddings-inference rerank 默认 max batch 32
KB_RERANK_MAX_BATCH_SIZE = max(1, int(os.environ.get("KB_RERANK_MAX_BATCH_SIZE") or "32"))


class KbRerankError(Exception):
    """资料库重排错误异常类型。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-25
    """
    pass


def rerank_enabled() -> bool:
    return bool(KB_RERANK_URL)


def _passage_text(item: dict) -> str:
    text = (item.get("text") or "").strip()
    ctx = (item.get("context_text") or "").strip()
    if ctx:
        return f"{text}\n\n{ctx}".strip()
    return text


def _parse_rerank_response(data: Any, n: int) -> list[tuple[int, float]]:
    if isinstance(data, list):
        if not data:
            return []
        if all(isinstance(x, (int, float)) for x in data):
            scored = [(i, float(s)) for i, s in enumerate(data[:n])]
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored
        if all(isinstance(x, dict) for x in data):
            scored: list[tuple[int, float]] = []
            for entry in data:
                idx = entry.get("index", entry.get("corpus_id"))
                if idx is None:
                    continue
                score = entry.get("score", entry.get("relevance_score", entry.get("similarity")))
                if score is None:
                    continue
                scored.append((int(idx), float(score)))
            if scored:
                scored.sort(key=lambda x: x[1], reverse=True)
                return scored
    if isinstance(data, dict):
        for key in ("results", "data", "rankings"):
            if key in data:
                return _parse_rerank_response(data[key], n)
    raise KbRerankError(f"无法解析 rerank 响应: {type(data).__name__}")


def _call_rerank_api(query: str, passages: list[str]) -> list[tuple[int, float]]:
    if not passages:
        return []
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if KB_RERANK_API_KEY:
        headers["Authorization"] = f"Bearer {KB_RERANK_API_KEY}"
    body_variants = [
        {"query": query, "texts": passages},
        {"query": query, "documents": passages},
        {"query": query, "passages": passages},
    ]
    last_err: Exception | None = None
    with httpx.Client(timeout=KB_RERANK_TIMEOUT_SEC) as client:
        for body in body_variants:
            try:
                resp = client.post(KB_RERANK_URL, json=body, headers=headers)
                resp.raise_for_status()
                return _parse_rerank_response(resp.json(), len(passages))
            except KbRerankError as exc:
                last_err = exc
            except httpx.HTTPError as exc:
                last_err = exc
    if last_err:
        raise KbRerankError(str(last_err)) from last_err
    return []


def rerank_hits(query: str, items: list[dict], *, top_k: int) -> tuple[list[dict], bool]:
    if not items:
        return [], False
    k = min(max(1, top_k), len(items))
    if not rerank_enabled():
        return items[:k], False

    # 仅对前 N 条候选调用 rerank（TEI 等服务有 batch 上限；items 已按检索分排序）
    batch_n = min(len(items), KB_RERANK_MAX_BATCH_SIZE)
    candidates = items[:batch_n]
    tail = items[batch_n:]

    passages = [_passage_text(it) for it in candidates]
    try:
        ranked = _call_rerank_api(query, passages)
    except (KbRerankError, httpx.HTTPError) as exc:
        logger.warning("kb rerank failed, passthrough: %s", exc)
        return items[:k], False

    if not ranked:
        return items[:k], False

    out: list[dict] = []
    seen: set[int] = set()
    for idx, score in ranked:
        if idx < 0 or idx >= len(candidates) or idx in seen:
            continue
        seen.add(idx)
        row = dict(candidates[idx])
        row["score"] = round(float(score), 4)
        row["rerank_score"] = row["score"]
        out.append(row)
        if len(out) >= k:
            break
    if len(out) < k:
        for i, it in enumerate(candidates):
            if i in seen:
                continue
            out.append(it)
            if len(out) >= k:
                break
    if len(out) < k:
        for it in tail:
            out.append(it)
            if len(out) >= k:
                break
    return out, True
