# Copyright (c) 2026 徐泽宇
"""072 P2：纯规则 RetrievalProfile 建议（无 LLM）。

与 skill/ding/agent/filex_langgraph_common.py 保持同步；修改须双边更新。
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

NUMERIC_Q = re.compile(r"金额|合计|价税|总计|多少|数字|日期|费用")
FIGURE_Q = re.compile(r"图里|流程图|示意图|截图|结构图|曲线图")
TOPIC_Q = re.compile(r"主题|关联|对比|还有哪些|相关文档|邻居")
STRUCT_REL_Q = re.compile(r"什么关系|怎么扯|引用链|涉及哪些主题|出链|入链|wiki-path")
TAG_TOPIC_Q = re.compile(r"共现|相邻标签|标签.*关联|关联.*标签")
CJK_DOC_Q = re.compile(r"发票|合同|报销单|报告")
TAG_Q = re.compile(r"标签下|归档在")
DUAL_ENTITY_Q = re.compile(
    r"(?P<left>.+?)\s*(?:和|与|跟)\s*(?P<right>.+?)\s*(?:之间\s*)?(?:什么关系|怎么扯|怎么关联|引用链)",
)


class QueryType(StrEnum):
    FACT = "fact"
    PROCEDURE = "procedure"
    CJK_DOC = "cjk_doc"
    STRUCTURED_FIELD = "structured_field"
    FULL_SUMMARY = "full_summary"
    TOPIC_WIKI = "topic_wiki"
    EXACT_TERM = "exact_term"
    FIGURE_VLM = "figure_vlm"
    TAG_ARCHIVE = "tag_archive"
    STRUCT_RELATION = "struct_relation"
    TAG_TOPIC = "tag_topic"


def classify_query_type(question: str) -> QueryType:
    q = (question or "").strip()
    if FIGURE_Q.search(q):
        return QueryType.FIGURE_VLM
    if STRUCT_REL_Q.search(q):
        return QueryType.STRUCT_RELATION
    if TAG_TOPIC_Q.search(q):
        return QueryType.TAG_TOPIC
    if TOPIC_Q.search(q):
        return QueryType.TOPIC_WIKI
    if NUMERIC_Q.search(q):
        return QueryType.STRUCTURED_FIELD
    if CJK_DOC_Q.search(q):
        return QueryType.CJK_DOC
    if TAG_Q.search(q):
        return QueryType.TAG_ARCHIVE
    if "步骤" in q or "流程" in q or "如何" in q:
        return QueryType.PROCEDURE
    if "全文" in q or "要点" in q or "清单" in q:
        return QueryType.FULL_SUMMARY
    if len(q) <= 12 and re.search(r"[\u4e00-\u9fff]", q):
        return QueryType.EXACT_TERM
    return QueryType.FACT


def parse_dual_entity_question(question: str) -> tuple[str, str] | None:
    q = (question or "").strip()
    match = DUAL_ENTITY_Q.search(q)
    if not match:
        return None
    left = match.group("left").strip().strip("「」\"'《》")
    right = match.group("right").strip().strip("「」\"'《》")
    if not left or not right:
        return None
    return left, right


def build_search_params_for_query_type(
    query_type: QueryType,
    user_question: str,
    *,
    tags: list[str] | None = None,
    tag_archive_union: bool = False,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "query": user_question,
        "top_k": 8,
        "group_by_file": True,
        "citation_format": "markdown",
        "context_chunks": 2,
    }
    if tags:
        base["tags"] = tags

    match query_type:
        case QueryType.FACT:
            base["context_chunks"] = 1
        case QueryType.PROCEDURE:
            base["context_chunks"] = 2
        case QueryType.CJK_DOC:
            base.update(filename_boost=True, query_expansion=True, context_chunks=2)
        case QueryType.STRUCTURED_FIELD:
            base["context_chunks"] = 3
        case QueryType.FULL_SUMMARY:
            base["top_k"] = 12
        case QueryType.TOPIC_WIKI:
            base.update(
                expand_wiki_links=True,
                expand_wiki_coref=True,
                wiki_context_depth=2,
            )
        case QueryType.STRUCT_RELATION:
            base.update(
                expand_wiki_links=True,
                expand_wiki_coref=False,
                wiki_context_depth=1,
                context_chunks=2,
            )
        case QueryType.TAG_TOPIC:
            base.update(
                expand_wiki_links=True,
                expand_wiki_coref=False,
                wiki_context_depth=1,
                expand_tag_cooc=True,
                context_chunks=2,
            )
        case QueryType.EXACT_TERM:
            base["query_expansion"] = False
            base["hybrid"] = True
        case QueryType.FIGURE_VLM:
            base.update(modality_boost=True, context_chunks=2)
        case QueryType.TAG_ARCHIVE:
            combine = "union" if tag_archive_union else "filter"
            base.update(tags=tags or [], tag_combine=combine)
        case _:
            pass

    return base


def use_query_cache_allowed(params: dict[str, Any]) -> bool:
    return not (
        params.get("expand_wiki_links")
        or params.get("expand_wiki_graph")
        or params.get("expand_tag_cooc")
    )


def suggest_retrieval_hints(query: str) -> dict[str, Any]:
    qtype = classify_query_type(query)
    params = build_search_params_for_query_type(qtype, query)
    dual = parse_dual_entity_question(query) if qtype == QueryType.STRUCT_RELATION else None

    notes: list[str] = []
    primary_path = "search"
    struct_relation_mode: str | None = None

    if qtype == QueryType.STRUCT_RELATION:
        if dual:
            primary_path = "wiki-path"
            struct_relation_mode = "dual_entity"
            notes.append(
                f"双实体关系问句：先解析「{dual[0]}」「{dual[1]}」为 file_id，"
                "再 GET /api/knowledge-base/wiki-path"
            )
        else:
            primary_path = "wiki-explain"
            struct_relation_mode = "single_entity"
            notes.append(
                "单点结构问句：LangGraph struct_relation_probe 先 wiki-explain，"
                "再降级 search（wiki_context_depth=1）"
            )
    elif qtype == QueryType.TAG_TOPIC:
        notes.append("L4b：expand_tag_cooc 与 L3 wiki_context_depth=1 同开")

    if not use_query_cache_allowed(params):
        notes.append("expand_wiki_* / expand_tag_cooc 开启时勿 use_query_cache")

    return {
        "query_type": qtype.value,
        "primary_path": primary_path,
        "struct_relation_mode": struct_relation_mode,
        "search_params": params,
        "use_query_cache_allowed": use_query_cache_allowed(params),
        "notes": notes,
    }
