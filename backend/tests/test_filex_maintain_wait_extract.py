# Copyright (c) 2026 徐泽宇
"""Unit tests for ding agent extract wait helpers.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import sys

import pytest
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parents[2] / "skill" / "ding" / "agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from filex_maintain_client import (  # noqa: E402
    is_terminal_extract_status,
    next_poll_interval,
    ws_kb_index_url,
)


def test_is_terminal_extract_status():
    assert is_terminal_extract_status("ready")
    assert is_terminal_extract_status("not_needed")
    assert is_terminal_extract_status("failed")
    assert not is_terminal_extract_status("pending")
    assert not is_terminal_extract_status("extracting")
    assert is_terminal_extract_status(None)


def test_next_poll_interval_backoff():
    assert next_poll_interval(0.4, min_interval=0.4, max_interval=2.5) == pytest.approx(0.56)
    assert next_poll_interval(2.0, min_interval=0.4, max_interval=2.5) == 2.5


def test_ws_kb_index_url():
    url = ws_kb_index_url("https://ding.example.top", "fb_test_key")
    assert url.startswith("wss://ding.example.top/api/ws/kb-index?token=")
    assert "fb_test_key" in url
