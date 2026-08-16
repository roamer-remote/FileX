# Copyright (c) 2026 徐泽宇
"""Chunk profile resolution.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from services.kb_chunk_profile import resolve_chunk_profile
from services.system_setting_service import KEY_KB_CHUNK_PROFILE, invalidate_settings_cache, update_settings


def test_resolve_chunk_profile_pdf_hint(db_session):
    p = resolve_chunk_profile(db_session, mime_type="application/pdf", original_name="a.pdf")
    assert p.name == "long_doc"


def test_resolve_chunk_profile_default(db_session):
    invalidate_settings_cache()
    update_settings(db_session, {KEY_KB_CHUNK_PROFILE: "default"})
    p = resolve_chunk_profile(db_session, mime_type="text/markdown", original_name="a.md")
    assert p.name == "default"
