# Copyright (c) 2026 徐泽宇
"""Unit tests for skill/ding/agent/filex_url_probe (no network).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import sys
from pathlib import Path

_AGENT = Path(__file__).resolve().parents[2] / "skill" / "ding" / "agent"
sys.path.insert(0, str(_AGENT))

from filex_url_probe import _classify, classify_magic  # noqa: E402


def test_classify_magic_pdf():
    assert classify_magic(b"%PDF-1.4\n") == "pdf"


def test_classify_magic_html():
    assert classify_magic(b"<!DOCTYPE html><html>") == "html"


def test_classify_html_content_type():
    assert (
        _classify(
            content_type="text/html; charset=utf-8",
            content_disposition=None,
            magic=None,
            url_ext=None,
        )
        == "html"
    )


def test_classify_attachment_pdf():
    assert (
        _classify(
            content_type="application/octet-stream",
            content_disposition='attachment; filename="paper.pdf"',
            magic=None,
            url_ext=None,
        )
        == "file"
    )


def test_classify_url_ext_pdf():
    assert (
        _classify(
            content_type=None,
            content_disposition=None,
            magic=None,
            url_ext=".pdf",
        )
        == "file"
    )
