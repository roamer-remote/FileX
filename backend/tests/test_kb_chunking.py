# Copyright (c) 2026 徐泽宇
"""kb chunking 相关测试模块。

Authors:
    徐泽宇
"""

from services.kb_chunking import chunk_text


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_short_paragraph():
    chunks = chunk_text("Hello world", chunk_size=100, overlap=10)
    assert len(chunks) == 1
    assert "Hello" in chunks[0].text


def test_chunk_text_strips_nul():
    chunks = chunk_text("hello\x00world", chunk_size=100, overlap=0)
    assert len(chunks) == 1
    assert "\x00" not in chunks[0].text
    assert "helloworld" in chunks[0].text
