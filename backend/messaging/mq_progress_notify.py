# Copyright (c) 2026 徐泽宇
"""Throttled progress notify publish from kb-indexer / kb-post workers."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

PROGRESS_NOTIFY_TYPES = frozenset({"kb_index_progress", "kb_post_progress"})
TERMINAL_NOTIFY_TYPES = frozenset({"kb_index_updated", "kb_post_updated", "kb_extract_updated"})

_throttle_lock = threading.Lock()
_throttle_state: dict[int, dict[str, Any]] = {}

MIN_INTERVAL_SEC = 1.0
MIN_PCT_DELTA = 5


def is_progress_notify(payload: dict) -> bool:
    return str(payload.get("type", "")) in PROGRESS_NOTIFY_TYPES


def is_terminal_kb_notify(payload: dict) -> bool:
    return str(payload.get("type", "")) in TERMINAL_NOTIFY_TYPES


def progress_notify_payload(
    *,
    notify_type: str,
    user_id: int,
    file_id: int,
    kind: str,
    progress_stage: str,
    progress_pct: int | None = None,
    progress_detail: str | None = None,
) -> dict:
    body: dict[str, Any] = {
        "type": notify_type,
        "user_id": int(user_id),
        "file_id": int(file_id),
        "kind": str(kind),
        "progress_stage": str(progress_stage),
    }
    if progress_pct is not None:
        body["progress_pct"] = int(max(0, min(100, progress_pct)))
    if progress_detail:
        body["progress_detail"] = str(progress_detail)
    return body


def _should_publish(file_id: int, progress_pct: int | None, progress_stage: str) -> bool:
    now = time.monotonic()
    with _throttle_lock:
        state = _throttle_state.get(int(file_id))
        if state is None:
            _throttle_state[int(file_id)] = {
                "last_ts": now,
                "last_pct": progress_pct,
                "last_stage": progress_stage,
            }
            return True
        if state.get("last_stage") != progress_stage:
            state["last_ts"] = now
            state["last_pct"] = progress_pct
            state["last_stage"] = progress_stage
            return True
        last_pct = state.get("last_pct")
        if progress_pct is not None and last_pct is not None:
            if abs(int(progress_pct) - int(last_pct)) >= MIN_PCT_DELTA:
                state["last_ts"] = now
                state["last_pct"] = progress_pct
                state["last_stage"] = progress_stage
                return True
        elif progress_pct is not None and last_pct is None:
            state["last_ts"] = now
            state["last_pct"] = progress_pct
            state["last_stage"] = progress_stage
            return True
        if now - float(state.get("last_ts", 0)) >= MIN_INTERVAL_SEC:
            state["last_ts"] = now
            state["last_pct"] = progress_pct
            state["last_stage"] = progress_stage
            return True
        return False


def clear_throttle_state(file_id: int) -> None:
    with _throttle_lock:
        _throttle_state.pop(int(file_id), None)


def maybe_publish_index_progress(
    *,
    user_id: int,
    file_id: int,
    progress_stage: str,
    progress_pct: int | None = None,
    progress_detail: str | None = None,
    force: bool = False,
) -> None:
    if not force and not _should_publish(file_id, progress_pct, progress_stage):
        return
    from messaging.kb_index_publisher import publish_kb_index_progress_notify

    payload = progress_notify_payload(
        notify_type="kb_index_progress",
        user_id=user_id,
        file_id=file_id,
        kind="kb_index",
        progress_stage=progress_stage,
        progress_pct=progress_pct,
        progress_detail=progress_detail,
    )
    try:
        publish_kb_index_progress_notify(payload)
    except Exception:
        logger.warning(
            "kb_index progress notify failed file_id=%s stage=%s",
            file_id,
            progress_stage,
            exc_info=True,
        )


def maybe_publish_post_progress(
    *,
    user_id: int,
    file_id: int,
    progress_stage: str,
    progress_pct: int | None = None,
    progress_detail: str | None = None,
    force: bool = False,
) -> None:
    if not force and not _should_publish(file_id, progress_pct, progress_stage):
        return
    from messaging.kb_post_publisher import publish_kb_post_progress_notify

    payload = progress_notify_payload(
        notify_type="kb_post_progress",
        user_id=user_id,
        file_id=file_id,
        kind="kb_post",
        progress_stage=progress_stage,
        progress_pct=progress_pct,
        progress_detail=progress_detail,
    )
    try:
        publish_kb_post_progress_notify(payload)
    except Exception:
        logger.warning(
            "kb_post progress notify failed file_id=%s stage=%s",
            file_id,
            progress_stage,
            exc_info=True,
        )
