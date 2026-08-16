# Copyright (c) 2026 徐泽宇
"""kb chunking structure 相关测试模块。

Authors:
    徐泽宇
"""

from services.kb_chunking import chunk_markdown


def test_chunk_markdown_preserves_heading_path():
    md = "# Root\n\nParagraph under root."
    chunks = chunk_markdown(md, chunk_size=500, overlap=0)
    assert chunks
    assert any(c.heading_path for c in chunks)
