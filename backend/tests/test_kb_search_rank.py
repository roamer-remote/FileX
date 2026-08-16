# Copyright (c) 2026 徐泽宇
"""kb_search_rank helpers.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from services.kb_search_rank import (
    apply_mmr,
    boost_keyword_bonus,
    build_or_tsquery_text,
    extract_query_terms,
)


def test_boost_keyword_bonus_substring():
    assert boost_keyword_bonus("OpenClaw 安装", "openclaw,agent") > 0
    assert boost_keyword_bonus("无关", "openclaw") == 0


def test_extract_query_terms_chinese_and_latin():
    terms = extract_query_terms("显微镜 imaging 原理")
    assert "显微镜" in terms
    assert "imaging" in terms
    assert "原理" in terms


def test_build_or_tsquery_text():
    assert build_or_tsquery_text(["显微镜", "成像"]) == "显微镜 | 成像"


def test_apply_mmr_reduces_same_file_neighbors():
    items = [
        {"file_id": 1, "chunk_index": 0, "text": "alpha beta", "score": 0.9},
        {"file_id": 1, "chunk_index": 1, "text": "alpha beta gamma", "score": 0.88},
        {"file_id": 2, "chunk_index": 0, "text": "totally different topic", "score": 0.7},
    ]
    out = apply_mmr(items, top_k=2, lambda_mult=0.7)
    assert len(out) == 2
    file_ids = {int(x["file_id"]) for x in out}
    assert 2 in file_ids
