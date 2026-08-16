# Copyright (c) 2026 徐泽宇
"""Citation pack formatting.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from services.kb_citation import attach_citations, format_hit_citation


def test_markdown_citation():
    s = format_hit_citation(
        {"file_id": 1, "chunk_id": 9, "chunk_index": 0, "original_name": "a.md", "text": "hello", "score": 0.8},
        fmt="markdown",
    )
    assert "filex://file/1" in s
    assert "chunk:9" in s


def test_attach_citations_json():
    out = attach_citations(
        [{"file_id": 1, "chunk_id": 2, "chunk_index": 0, "original_name": "x", "text": "t", "score": 1.0}],
        "json",
    )
    assert out[0]["citation"]["file_id"] == 1
