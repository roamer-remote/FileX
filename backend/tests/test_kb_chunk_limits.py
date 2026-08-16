# Copyright (c) 2026 徐泽宇
"""061 P0-C: embedder cap and effective chunk params."""

from __future__ import annotations

import pytest

from models.file import File as FileModel
from services.kb_chunk_profile import resolve_effective_chunk_params
from services.kb_embed_limits import max_chars_for_model
from services.system_setting_service import (
    KEY_KB_CHUNK_OVERLAP,
    KEY_KB_CHUNK_PROFILE,
    KEY_KB_CHUNK_SIZE,
    invalidate_settings_cache,
    update_settings,
)


def test_max_chars_for_model_bge_m3():
    assert max_chars_for_model("bge-m3:latest") == 8192
    assert max_chars_for_model("unknown-model") == 8192


def test_resolve_effective_chunk_params_caps_size(db_session, regular_user):
    f = FileModel(
        filename="a.bin",
        original_name="doc.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    invalidate_settings_cache()
    update_settings(db_session, {KEY_KB_CHUNK_SIZE: "100000"})
    params = resolve_effective_chunk_params(db_session, f)
    assert params.chunk_size == 8192
    assert params.effective_max_chars == 8192


def test_overlap_must_be_less_than_size(db_session):
    invalidate_settings_cache()
    update_settings(db_session, {KEY_KB_CHUNK_SIZE: "500", KEY_KB_CHUNK_OVERLAP: "100"})
    with pytest.raises(ValueError, match="kb_chunk_overlap"):
        invalidate_settings_cache()
        update_settings(db_session, {KEY_KB_CHUNK_SIZE: "500", KEY_KB_CHUNK_OVERLAP: "500"})


def test_split_long_segment_recursive_preserves_content():
    from services.kb_chunking import _split_long_segment_recursive

    segment = "AB。" * 200
    pieces = _split_long_segment_recursive(segment, size=100, overlap=0)
    assert pieces
    assert sum(len(x) for x in pieces) >= len(segment) - 10


def test_overlap_validated_against_profile_when_size_unset(db_session):
    invalidate_settings_cache()
    update_settings(
        db_session,
        {KEY_KB_CHUNK_PROFILE: "qa_pairs", KEY_KB_CHUNK_OVERLAP: "500", KEY_KB_CHUNK_SIZE: ""},
    )
    invalidate_settings_cache()
    with pytest.raises(ValueError, match="kb_chunk_overlap"):
        update_settings(db_session, {KEY_KB_CHUNK_OVERLAP: "512"})


# T-4 large document chunking tests
def test_large_pdf_md_chars_gets_bigger_chunks(db_session, regular_user):
    """T-4: PDF with >400k md_chars should get >=1800 chunk_size (long_doc path)."""
    from services.system_setting_service import KEY_KB_CHUNK_PROFILE

    f = FileModel(
        filename="annual.pdf",
        original_name="平安银行2025年报.pdf",
        file_path="/tmp/annual.pdf",
        file_size=2000000,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()

    invalidate_settings_cache()
    # Force long_doc profile via system (or rely on mime hint)
    update_settings(db_session, {KEY_KB_CHUNK_PROFILE: "long_doc"})

    params_large = resolve_effective_chunk_params(db_session, f, md_char_count=550_000)
    assert params_large.chunk_size >= 1800, f"expected >=1800 for large pdf, got {params_large.chunk_size}"

    params_small = resolve_effective_chunk_params(db_session, f, md_char_count=50_000)
    # small doc keeps the profile default (1200 for long_doc before cap)
    assert params_small.chunk_size <= 1200 or params_small.chunk_size < params_large.chunk_size


def test_non_large_doc_unchanged_chunk_size(db_session, regular_user):
    """Small docs and non-PDF should not be affected by T-4 large logic."""
    f = FileModel(
        filename="small.txt",
        original_name="notes.txt",
        file_path="/tmp/small.txt",
        file_size=1000,
        mime_type="text/plain",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()

    invalidate_settings_cache()
    params = resolve_effective_chunk_params(db_session, f, md_char_count=3000)
    # Should be the default/system size (capped), not forced to 1800
    assert params.chunk_size < 1800 or params.chunk_size == 1200  # typical long_doc or default before cap
