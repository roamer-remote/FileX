# Copyright (c) 2026 徐泽宇
"""Built-in CJK query expansion for short domain terms (007 P3).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

CJK_EXPANSION_MAP: dict[str, list[str]] = {
    "发票": ["发票", "报销", "收据", "单据", "对账单"],
    "合同": ["合同", "协议", "合约", "契约"],
    "报告": ["报告", "报表", "汇报", "分析报告"],
    "简历": ["简历", "履历", "CV", "个人简历"],
    "教程": ["教程", "指南", "手册", "说明", "文档"],
}


def expand_query_terms(query: str) -> tuple[list[str], list[str]]:
    """Return (search_terms, expanded_terms_for_meta). Empty expansion → single original query."""
    q = query.strip()
    if not q or len(q) > 4:
        return [q], []
    mapped = CJK_EXPANSION_MAP.get(q)
    if not mapped:
        return [q], []
    seen: set[str] = set()
    terms: list[str] = []
    for term in mapped:
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)
    if len(terms) <= 1:
        return [q], []
    return terms, terms


def merge_rrf_rankings(rankings: list[list[int]], *, k: int = 60) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranked in rankings:
        for rank, cid in enumerate(ranked):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return scores
