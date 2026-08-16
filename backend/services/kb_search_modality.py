# Copyright (c) 2026 徐泽宇
"""Modality intent detection and content_kind boost (030 P1)."""

from __future__ import annotations

from models.kb_enums import ContentKind

_FIGURE_TERMS = (
    "图片",
    "插图",
    "示意图",
    "照片",
    "figure",
    "image",
    "diagram",
    "photo",
    "picture",
)
_TABLE_TERMS = (
    "表格",
    "table",
    "清单",
)
_EQUATION_TERMS = (
    "公式",
    "方程",
    "equation",
    "formula",
    "latex",
)
_TEXT_TERMS = (
    "正文",
    "文字",
    "段落",
    "text",
)


def _query_matches_term(query: str, term: str) -> bool:
    if not term:
        return False
    if term.isascii():
        return term.lower() in query.lower()
    return term in query


def detect_modality_intent(query: str) -> list[str]:
    """Rule-based modality intent from natural language query."""
    q = (query or "").strip()
    if not q:
        return []
    intents: list[str] = []
    if any(_query_matches_term(q, t) for t in _FIGURE_TERMS):
        intents.append(ContentKind.figure.value)
    if any(_query_matches_term(q, t) for t in _TABLE_TERMS):
        intents.append(ContentKind.table.value)
    if any(_query_matches_term(q, t) for t in _EQUATION_TERMS):
        intents.append(ContentKind.equation.value)
    if any(_query_matches_term(q, t) for t in _TEXT_TERMS):
        intents.append(ContentKind.text.value)
    return intents


def apply_modality_boost_scores(
    items: list[dict],
    intent: list[str],
    *,
    boost_value: float,
    debug: bool = False,
) -> None:
    if boost_value <= 0 or not intent:
        return
    intent_set = set(intent)
    intent_set.discard(ContentKind.text.value)
    if not intent_set:
        return
    for item in items:
        kind = item.get("content_kind")
        if not kind or kind not in intent_set:
            continue
        if debug and "base_score" not in item:
            item["base_score"] = round(float(item["score"]), 4)
        item["score"] = round(float(item["score"]) + boost_value, 4)
        item["modality_boost"] = round(boost_value, 4)
