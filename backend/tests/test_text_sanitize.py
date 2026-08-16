# Copyright (c) 2026 徐泽宇
"""text sanitize 相关测试模块。

Authors:
    徐泽宇
"""

from utils.text_sanitize import strip_nul_bytes


def test_strip_nul_bytes():
    assert strip_nul_bytes("hello") == "hello"
    assert strip_nul_bytes("a\x00b\x00c") == "abc"
    assert strip_nul_bytes("") == ""
