# Copyright (c) 2026 徐泽宇
"""Agent-facing API freshness: timestamps and no-cache headers.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Response

AGENT_KB_SEARCH_NOTICE = (
    "检索快照仅在本响应时刻有效；用户可能已删除或移动文件，"
    "勿将会话历史中的旧命中当作当前资料库状态，每轮须重新调用本接口。"
)

AGENT_KB_SEARCH_CITATION_NOTICE = (
    " 若依据本响应 items/wiki_context/GET md 作答：须在回复中向用户披露引用来源，"
    "每条依据使用对应 citation_label（如《合同.pdf》第 12 页、《报表.xlsx》第 2 个工作表「汇总》），"
    "禁止只给结论不标注出处，禁止编造页码/张/工作表名，禁止向用户暴露 file_id 或 score。"
)

AGENT_KB_SEARCH_WIKI_CONTEXT_APPENDIX = (
    " 若 wiki_context_hint.expandable_seed_ids 非空：主 Agent 用 curl 调 "
    "GET /api/files/{file_id}/wiki-context?depth=1&max_files=8 并合并 nodes[].markdown；"
    "recommended_parallel≥2 时同轮并行多条 curl（勿派子 Agent）；"
    "expandable 为空则跳过 wiki-context。"
)

AGENT_FILE_VERIFY_NOTICE = (
    "文件状态以本响应为准；若返回 404 表示已删除或无权访问，"
    "勿使用会话历史中的旧文件内容。"
)


def utc_now_iso_z() -> str:
    """ISO 8601 UTC timestamp with Z suffix (second precision)."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def apply_agent_no_cache_headers(response: Response) -> None:
    """Prevent proxies and clients from reusing stale KB / file verification responses."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
