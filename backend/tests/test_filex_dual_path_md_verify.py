# Copyright (c) 2026 徐泽宇
"""Unit tests for dual-path markdown validation helpers.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import sys
from pathlib import Path

_AGENT_DIR = Path(__file__).resolve().parents[2] / "skill" / "ding" / "agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from filex_maintain_client import (  # noqa: E402
    normalize_md,
    validate_draft,
    verify_md_written,
)


def test_normalize_md_strips_and_unifies_newlines():
    assert normalize_md("a\r\nb\r\n") == "a\nb"


def test_validate_draft_requires_summary():
    ok, reason = validate_draft("# Title\n\nbody", require_summary=True)
    assert not ok
    assert "总结" in reason

    content = "# Title\n\nbody\n\n## 总结\n\n要点"
    ok, reason = validate_draft(content, require_summary=True)
    assert ok
    assert reason == "ok"


def test_verify_md_written_exact_match():
    draft = "# Title\n\n正文\n\n## 总结\n\n要点"
    ok, _ = verify_md_written(draft, draft, require_summary=True)
    assert ok

    ok, reason = verify_md_written(draft + "\n", draft, require_summary=True)
    assert ok

    mismatched = "# Title\n\n别的正文\n\n## 总结\n\n要点"
    ok, reason = verify_md_written(mismatched, draft, require_summary=True)
    assert not ok
    assert "不一致" in reason
