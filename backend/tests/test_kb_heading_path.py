# Copyright (c) 2026 徐泽宇
"""Tests for kb_heading_path (038)."""

from services.kb_heading_path import (
    KB_HEADING_CODE_HEURISTIC_MIN_LEN,
    KB_HEADING_PATH_MAX_LEN,
    KB_HEADING_TITLE_MAX_LEN,
    cap_heading_path,
    is_valid_markdown_heading_title,
    looks_like_code_heading,
)


def test_cap_heading_path_none_and_empty():
    assert cap_heading_path(None) is None
    assert cap_heading_path("") is None
    assert cap_heading_path("   ") is None


def test_cap_heading_path_unchanged_within_limit():
    s = "正常标题 > 子节"
    assert cap_heading_path(s) == s
    assert cap_heading_path("x" * 512) == "x" * 512


def test_cap_heading_path_truncates_to_512():
    long = "x" * 600
    capped = cap_heading_path(long)
    assert capped is not None
    assert len(capped) == KB_HEADING_PATH_MAX_LEN
    assert capped == "x" * 512


def test_cap_heading_path_utf8_multibyte_safe_char_slice():
    s = "中" * 600
    capped = cap_heading_path(s)
    assert capped is not None
    assert len(capped) == 512


def test_looks_like_code_heading_only_when_len_between_80_and_200():
    short_def = "def foo(): pass"
    assert len(short_def) <= KB_HEADING_CODE_HEURISTIC_MIN_LEN
    assert looks_like_code_heading(short_def) is False

    long_def = "x" * 81 + " def foo():"
    assert looks_like_code_heading(long_def) is True

    over_max = "x" * (KB_HEADING_TITLE_MAX_LEN + 1) + " def foo():"
    assert looks_like_code_heading(over_max) is False


def test_looks_like_code_heading_heuristics_h04_app_decorator():
    mid = "y" * 100 + ' @app.get("/x")'
    assert 80 < len(mid) <= 200
    assert looks_like_code_heading(mid) is True


def test_is_valid_markdown_heading_title_rejects_empty():
    assert is_valid_markdown_heading_title("") is False
    assert is_valid_markdown_heading_title("   ") is False


def test_is_valid_markdown_heading_title_whitelist_short_keywords():
    assert is_valid_markdown_heading_title("import 指南") is True
    assert is_valid_markdown_heading_title("A -> B") is True
    assert is_valid_markdown_heading_title("from 入门") is True


def test_is_valid_markdown_heading_title_rejects_over_200():
    assert is_valid_markdown_heading_title("a" * 201) is False


def test_is_valid_markdown_heading_title_rejects_code_like_long_line():
    title = "SPA 路由：" + "x" * 100 + ' @app.get("/{path:path}") def serve(): pass'
    assert len(title) > KB_HEADING_CODE_HEURISTIC_MIN_LEN
    assert is_valid_markdown_heading_title(title) is False
