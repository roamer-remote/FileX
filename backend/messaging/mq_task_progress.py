# Copyright (c) 2026 徐泽宇
"""In-memory MQ task progress registry (filex API process only).

Workers publish progress notify messages; kb_index_notify consumer writes here.
_active_tasks_global merges registry fields into running tasks for WS/REST.
"""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_registry: dict[int, dict[str, Any]] = {}


def set_progress(
    file_id: int,
    *,
    kind: str,
    progress_stage: str,
    progress_pct: int | None = None,
    progress_detail: str | None = None,
) -> None:
    entry: dict[str, Any] = {
        "kind": str(kind),
        "progress_stage": str(progress_stage),
    }
    if progress_pct is not None:
        entry["progress_pct"] = int(max(0, min(100, progress_pct)))
    if progress_detail:
        entry["progress_detail"] = str(progress_detail)
    with _lock:
        _registry[int(file_id)] = entry


def clear_progress(file_id: int) -> None:
    with _lock:
        _registry.pop(int(file_id), None)


def get_progress(file_id: int) -> dict[str, Any] | None:
    with _lock:
        entry = _registry.get(int(file_id))
        return dict(entry) if entry else None


def merge_task_progress(task: dict) -> dict:
    file_id = task.get("file_id")
    if file_id is None:
        return task
    entry = get_progress(int(file_id))
    if not entry:
        return task
    if str(entry.get("kind", "")) and str(entry["kind"]) != str(task.get("kind", "")):
        return task
    out = dict(task)
    for key in ("progress_pct", "progress_stage", "progress_detail"):
        if key in entry and entry[key] is not None:
            out[key] = entry[key]
    return out


def merge_task_progress_list(tasks: list[dict]) -> list[dict]:
    return [merge_task_progress(task) for task in tasks]


def prune_stale_progress(active_file_ids: set[int]) -> None:
    """Drop registry entries when DB no longer has a running task (worker crash, no terminal notify)."""
    with _lock:
        stale = [fid for fid in _registry if fid not in active_file_ids]
        for fid in stale:
            _registry.pop(fid, None)
