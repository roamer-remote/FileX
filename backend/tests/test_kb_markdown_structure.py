# Copyright (c) 2026 徐泽宇
"""Tests for kb_markdown_structure (038)."""

from services.kb_heading_path import cap_heading_path
from services.kb_markdown_structure import split_markdown_blocks


def _file_266_pseudo_line() -> str:
    """552-char MinerU mis-OCR heading line (file_id=266 production sample)."""
    base = "# SPA 路由："
    suffix = ' @app.get("/{path:path}") def serve_frontend(): pass'
    filler_len = 552 - len(base) - len(suffix)
    return base + ("x" * filler_len) + suffix


def test_sc_038_001_pseudo_heading_not_heading_block():
    line = _file_266_pseudo_line()
    assert len(line) == 552
    md = f"{line}\n\n后续段落。"
    blocks = split_markdown_blocks(md)
    assert not any(b.block_type == "heading" and "SPA 路由" in b.text for b in blocks)
    paras = [b for b in blocks if "后续段落" in b.text]
    assert paras
    assert paras[0].heading_path is None


def test_sc_038_002_nested_heading_path():
    md = "# 正常标题\n\n## 子节\n\n正文"
    blocks = split_markdown_blocks(md)
    body = [b for b in blocks if "正文" in b.text][0]
    assert body.heading_path == "正常标题 > 子节"


def test_sc_038_005_fence_heading_not_in_stack():
    md = "```\n# not a real heading\n```\n\nafter"
    blocks = split_markdown_blocks(md)
    after = [b for b in blocks if "after" in b.text][0]
    assert after.heading_path is None


def test_sc_038_009_whitelist_short_code_like_titles_remain_heading():
    for title in ("import 指南", "A -> B", "from 入门"):
        blocks = split_markdown_blocks(f"# {title}\n\nbody")
        headings = [b for b in blocks if b.block_type == "heading"]
        assert len(headings) == 1, title
        assert headings[0].text.strip() == f"# {title}"


def test_sc_038_008_nested_4x150_path_capped_for_db():
    t150 = "章" * 150
    md = f"# {t150}\n\n## {t150}\n\n### {t150}\n\n#### {t150}\n\n段落。"
    blocks = split_markdown_blocks(md)
    body = [b for b in blocks if "段落" in b.text][0]
    assert body.heading_path is not None
    assert len(body.heading_path) > 512
    capped = cap_heading_path(body.heading_path)
    assert capped is not None
    assert len(capped) == 512


def test_split_heading_and_table():
    md = "# Title\n\n## Section\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    blocks = split_markdown_blocks(md)
    assert len(blocks) >= 2
    types = {b.block_type for b in blocks}
    assert "heading" in types or "paragraph" in types
