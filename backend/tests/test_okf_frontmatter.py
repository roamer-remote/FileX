# Copyright (c) 2026 徐泽宇
"""OKF frontmatter unit tests."""

from services.okf.frontmatter import merge_frontmatter, normalize_metadata_for_storage, split_frontmatter


def test_split_frontmatter_roundtrip():
    raw = "---\ntype: Table\ntitle: Orders\ntags: [a]\n---\n\n# Body\n"
    meta, body = split_frontmatter(raw)
    assert meta["type"] == "Table"
    assert "# Body" in body
    out = merge_frontmatter(normalize_metadata_for_storage(meta), "Table", body)
    meta2, body2 = split_frontmatter(out)
    assert meta2["type"] == "Table"
    assert meta2["title"] == "Orders"
    assert "# Body" in body2


def test_normalize_strips_type():
    stored = normalize_metadata_for_storage({"type": "X", "title": "T", "tags": "one"})
    assert "type" not in stored
    assert stored["tags"] == ["one"]
