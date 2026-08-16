# Copyright (c) 2026 徐泽宇
"""KB extract/index pipeline operation logs (067)."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

from services.log_service import log_operation

logger = structlog.get_logger(__name__)

TARGET_TYPE_FILE = "file"
DETAIL_MAX_LEN = 2000
ACTION_MAX_LEN = 50
DETAIL_TRUNC_SUFFIX = "…"

# Appendix A — authoritative Chinese actions (spec 067)
ACTION_KB_EXTRACT_START = "KB 提取开始"
ACTION_KB_EXTRACT_DONE = "KB 提取完成"
ACTION_KB_EXTRACT_ERROR = "KB 提取失败"
ACTION_KB_EXTRACT_FALLBACK = "KB 提取失败回退"
ACTION_KB_EXTRACT_SKIP = "KB 提取跳过"
ACTION_KB_EXTRACT_DEFER = "KB 提取延后"
ACTION_INSAVLO_SUBMIT = "Insavlo 远程提交"
ACTION_INSAVLO_WEBHOOK_RECEIVED = "Insavlo Webhook 收到"
ACTION_INSAVLO_WRITEBACK_DONE = "Insavlo 写回完成"
ACTION_INSAVLO_WRITEBACK_ERROR = "Insavlo 写回失败"
ACTION_INSAVLO_WEBHOOK_TIMEOUT = "Insavlo Webhook 超时"
ACTION_KB_INDEX_START = "KB 索引开始"
ACTION_KB_INDEX_DONE = "KB 索引完成"
ACTION_KB_INDEX_ERROR = "KB 索引失败"
ACTION_KB_INDEX_SKIP = "KB 索引跳过"
ACTION_KB_INDEX_RECOVER = "KB 索引恢复"
ACTION_KB_RAPTOR_WARN = "KB RAPTOR 警告"
ACTION_KB_POST_START = "KB 后处理开始"
ACTION_KB_POST_DONE = "KB 后处理完成"
ACTION_KB_POST_SKIP = "KB 后处理跳过"
ACTION_KB_POST_ERROR = "KB 后处理失败"
ACTION_KB_POST_RECOVER = "KB 后处理恢复"
ACTION_KB_FORCE_RAPTOR_START = "KB 强制 RAPTOR 开始"
ACTION_KB_FORCE_RAPTOR_DONE = "KB 强制 RAPTOR 完成"
ACTION_KB_FORCE_RAPTOR_WARN = "KB 强制 RAPTOR 警告"
ACTION_KB_FORCE_RAPTOR_SKIP = "KB 强制 RAPTOR 跳过"

ALL_PIPELINE_ACTIONS = (
    ACTION_KB_EXTRACT_START,
    ACTION_KB_EXTRACT_DONE,
    ACTION_KB_EXTRACT_ERROR,
    ACTION_KB_EXTRACT_FALLBACK,
    ACTION_KB_EXTRACT_SKIP,
    ACTION_KB_EXTRACT_DEFER,
    ACTION_INSAVLO_SUBMIT,
    ACTION_INSAVLO_WEBHOOK_RECEIVED,
    ACTION_INSAVLO_WRITEBACK_DONE,
    ACTION_INSAVLO_WRITEBACK_ERROR,
    ACTION_INSAVLO_WEBHOOK_TIMEOUT,
    ACTION_KB_INDEX_START,
    ACTION_KB_INDEX_DONE,
    ACTION_KB_INDEX_ERROR,
    ACTION_KB_INDEX_SKIP,
    ACTION_KB_INDEX_RECOVER,
    ACTION_KB_RAPTOR_WARN,
    ACTION_KB_POST_START,
    ACTION_KB_POST_DONE,
    ACTION_KB_POST_SKIP,
    ACTION_KB_POST_ERROR,
    ACTION_KB_POST_RECOVER,
    ACTION_KB_FORCE_RAPTOR_START,
    ACTION_KB_FORCE_RAPTOR_DONE,
    ACTION_KB_FORCE_RAPTOR_WARN,
    ACTION_KB_FORCE_RAPTOR_SKIP,
)


def pipeline_reason(message: str | None, max_len: int = 500) -> str:
    """Sanitize free-text for key=value detail (spaces → underscores)."""
    return str(message or "").replace(" ", "_")[:max_len]


def _format_detail_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _truncate_detail(text: str) -> str:
    if len(text) <= DETAIL_MAX_LEN:
        return text
    keep = DETAIL_MAX_LEN - len(DETAIL_TRUNC_SUFFIX)
    if keep < 0:
        keep = 0
    return text[:keep] + DETAIL_TRUNC_SUFFIX


def format_kb_pipeline_detail(**fields: Any) -> str:
    """Build ``key=value`` detail text; keys sorted alphabetically; truncate to DETAIL_MAX_LEN.

    Values should not contain spaces; use underscores in free-text fields (e.g. ``reason``).
    """
    parts: list[str] = []
    for key in sorted(fields):
        value = fields[key]
        if value is None:
            continue
        parts.append(f"{key}={_format_detail_value(value)}")
    return _truncate_detail(" ".join(parts))


def _truncate_action(action: str) -> str:
    return (action or "")[:ACTION_MAX_LEN]


def log_kb_pipeline_event(
    db: Session,
    user_id: int,
    action: str,
    file_id: int,
    detail: str | None = None,
    *,
    commit: bool = False,
) -> None:
    """Write one pipeline event to operation_logs; failures must not break callers.

    Pipeline events always target a file; ``file_id`` is required. For system-level events
    without a file association, extend the signature before calling.
    """
    safe_action = _truncate_action(action)
    safe_detail = _truncate_detail(detail) if detail else detail
    try:
        log_operation(
            db,
            user_id,
            safe_action,
            target_type=TARGET_TYPE_FILE,
            target_id=file_id,
            detail=safe_detail,
            commit=commit,
        )
    except Exception:
        logger.warning(
            "kb_pipeline_log_failed user_id=%s action=%s file_id=%s",
            user_id,
            safe_action,
            file_id,
            exc_info=True,
        )
