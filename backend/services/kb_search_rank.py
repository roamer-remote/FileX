# Copyright (c) 2026 徐泽宇
"""Retrieval ranking helpers: boost keywords, MMR diversity, query term extraction.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import re

from config import KB_SEARCH_BOOST_KEYWORD_BONUS, KB_SEARCH_MMR_LAMBDA

_BOOST_SPLIT = re.compile(r"[,;\n]+")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")
_LATIN_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{1,}")


def parse_boost_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip().lower() for p in _BOOST_SPLIT.split(raw) if p and p.strip()]


def boost_keyword_bonus(
    query: str,
    boost_keywords: str | None,
    *,
    bonus_per_hit: float | None = None,
) -> float:
    """查询与 chunk.boost_keywords 命中时加分（子串或整词）。"""
    per_hit = KB_SEARCH_BOOST_KEYWORD_BONUS if bonus_per_hit is None else bonus_per_hit
    keywords = parse_boost_keywords(boost_keywords)
    if not keywords:
        return 0.0
    q = query.strip().lower()
    if not q:
        return 0.0
    hits = 0
    for kw in keywords:
        if kw in q or q in kw:
            hits += 1
            continue
        if " " in q and kw in q.split():
            hits += 1
    if hits == 0:
        return 0.0
    return min(0.25, hits * per_hit)


def apply_boost_keyword_scores(
    items: list[dict],
    query: str,
    *,
    bonus_per_hit: float | None = None,
) -> None:
    for item in items:
        bonus = boost_keyword_bonus(query, item.get("boost_keywords"), bonus_per_hit=bonus_per_hit)
        if bonus <= 0:
            continue
        item["score"] = round(float(item["score"]) + bonus, 4)
        item["keyword_boost"] = round(bonus, 4)


def filename_boost_bonus(
    query: str,
    original_name: str | None,
    *,
    boost_value: float | None = None,
) -> float:
    per_hit = KB_SEARCH_FILENAME_BOOST if boost_value is None else boost_value
    if per_hit <= 0:
        return 0.0
    q = query.strip()
    name = (original_name or "").strip()
    if not q or not name:
        return 0.0
    if q.lower() in name.lower():
        return per_hit
    return 0.0


def apply_filename_boost_scores(
    items: list[dict],
    query: str,
    *,
    boost_value: float,
    debug: bool = False,
) -> None:
    for item in items:
        bonus = filename_boost_bonus(query, item.get("original_name"), boost_value=boost_value)
        if bonus <= 0:
            continue
        if debug:
            item["base_score"] = round(float(item["score"]), 4)
        item["score"] = round(float(item["score"]) + bonus, 4)
        item["filename_boost"] = round(bonus, 4)


def extract_query_terms(query: str, *, max_terms: int = 6) -> list[str]:
    """从自然语言查询抽取 FTS 用词（中英文），用于混合检索 OR 扩展。"""
    terms: list[str] = []
    terms.extend(_CJK_RUN.findall(query))
    terms.extend(w.lower() for w in _LATIN_WORD.findall(query))
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= max_terms:
            break
    return out


def build_or_tsquery_text(terms: list[str]) -> str | None:
    safe_parts: list[str] = []
    for term in terms:
        cleaned = re.sub(r"[&|!():*\'\"]", " ", term).strip()
        if cleaned:
            safe_parts.append(cleaned)
    if not safe_parts:
        return None
    return " | ".join(safe_parts)


def _token_set(text: str) -> set[str]:
    return {t for t in re.split(r"\s+", (text or "").lower()) if len(t) > 1}


def _text_jaccard(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _mmr_pair_sim(a: dict, b: dict) -> float:
    if int(a["file_id"]) == int(b["file_id"]):
        gap = abs(int(a["chunk_index"]) - int(b["chunk_index"]))
        if gap == 0:
            return 1.0
        if gap == 1:
            return 0.85
        return min(1.0, 0.45 + 0.45 * _text_jaccard(a.get("text", ""), b.get("text", "")))
    return _text_jaccard(a.get("text", ""), b.get("text", "")) * 0.65


def apply_mmr(items: list[dict], *, top_k: int, lambda_mult: float | None = None) -> list[dict]:
    """MMR 去重：降低同文件相邻块占满 top_k 的情况。"""
    lam = KB_SEARCH_MMR_LAMBDA if lambda_mult is None else lambda_mult
    lam = max(0.0, min(1.0, lam))
    if len(items) <= 1 or top_k <= 0:
        return items[:top_k]
    pool = sorted(items, key=lambda x: float(x["score"]), reverse=True)
    selected: list[dict] = []
    remaining = list(pool)
    while remaining and len(selected) < top_k:
        if not selected:
            selected.append(remaining.pop(0))
            continue
        best_idx = 0
        best_mmr = float("-inf")
        for i, cand in enumerate(remaining):
            rel = float(cand["score"])
            max_sim = max(_mmr_pair_sim(cand, picked) for picked in selected)
            mmr = lam * rel - (1.0 - lam) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i
        selected.append(remaining.pop(best_idx))
    return selected
