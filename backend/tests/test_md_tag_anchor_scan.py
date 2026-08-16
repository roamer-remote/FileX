# Copyright (c) 2026 徐泽宇
"""md tag anchor scan 相关测试模块。

Authors:
    徐泽宇
"""

from services.md_tag_anchor_scan import iter_tag_occurrences_in_markdown


def test_skips_fenced_code():
    md = "# t\n\nhello alpha\n\n```\nalpha beta\n```\n\nmore alpha"
    spans = iter_tag_occurrences_in_markdown(md, "alpha")
    assert len(spans) == 2
    assert md[spans[0][0] : spans[0][1]] == "alpha"
    assert md[spans[1][0] : spans[1][1]] == "alpha"


def test_skips_inline_code():
    md = "use `alpha` but real alpha here"
    spans = iter_tag_occurrences_in_markdown(md, "alpha")
    assert len(spans) == 1


def test_case_insensitive():
    md = "Alpha and alpha"
    spans = iter_tag_occurrences_in_markdown(md, "alpha")
    assert len(spans) == 2
    assert md[spans[0][0] : spans[0][1]] == "Alpha"
    assert md[spans[1][0] : spans[1][1]] == "alpha"
