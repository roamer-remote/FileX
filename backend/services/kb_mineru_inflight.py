# Copyright (c) 2026 徐泽宇
"""In-flight MinerU MQ RPC tasks for admin MQ monitor (032 PR-B)."""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_inflight: dict[int, dict[str, Any]] = {}


def register_mineru_inflight(
    *,
    file_id: int,
    job_id: int | None,
    filename: str,
    username: str | None = None,
) -> None:
    with _lock:
        _inflight[int(file_id)] = {
            "file_id": int(file_id),
            "job_id": job_id,
            "filename": filename,
            "username": (username or "").strip() or None,
        }


def clear_mineru_inflight(file_id: int) -> None:
    with _lock:
        _inflight.pop(int(file_id), None)


def list_mineru_inflight() -> list[dict[str, Any]]:
    with _lock:
        return list(_inflight.values())


def reset_mineru_inflight_for_tests() -> None:
    """Test helper only."""
    with _lock:
        _inflight.clear()
