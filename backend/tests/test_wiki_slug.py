# Copyright (c) 2026 徐泽宇
"""wiki slug 相关测试模块。

Authors:
    徐泽宇
"""

import pytest

from utils.wiki_slug import normalize_wiki_slug


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("重要人才", "重要人才"),
        ("CRISPR 基因编辑", "crispr-基因编辑"),
        ("crispr-gene-editing", "crispr-gene-editing"),
        ("  VIP  ", "vip"),
        ("ＣＲＩＳＰＲ", "crispr"),
        ("重要__人才", "重要-人才"),
        ("", ""),
        ("---", ""),
        ("|invalid|", "invalid"),
    ],
)
def test_normalize_wiki_slug(raw: str, expected: str) -> None:
    assert normalize_wiki_slug(raw) == expected


def test_normalize_wiki_slug_truncates_to_128_chars() -> None:
    raw = "中" * 200
    assert len(normalize_wiki_slug(raw)) == 128
