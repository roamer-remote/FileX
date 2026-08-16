# Copyright (c) 2026 徐泽宇
"""KB_SEARCH_MIN_SCORE filters low-similarity vector hits.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from services.kb_chunk_embed_input import build_embed_input
from services.kb_search_service import _passes_min_score


def test_passes_min_score_filters_low_vector():
    assert (
        _passes_min_score({"vector_score": 0.5, "chunk_id": 1}, min_score=0.6, fts_chunk_ids=set())
        is False
    )
    assert (
        _passes_min_score({"vector_score": 0.8, "chunk_id": 1}, min_score=0.6, fts_chunk_ids=set())
        is True
    )


def test_passes_min_score_keeps_fts_hits():
    assert (
        _passes_min_score({"vector_score": 0.1, "chunk_id": 7}, min_score=0.6, fts_chunk_ids={7})
        is True
    )


def test_build_embed_input_includes_heading_in_header():
    out = build_embed_input(
        body="body",
        heading_path="H1 > H2",
        workspace_name=None,
        tags=[],
        content_kind=None,
        original_name=None,
    )
    assert "heading: H1 > H2" in out
    assert out.endswith("body")
    assert out.startswith("---")
