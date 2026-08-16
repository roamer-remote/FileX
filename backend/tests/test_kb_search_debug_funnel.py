# Copyright (c) 2026 徐泽宇
"""048 debug_funnel ACL-after counts."""

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_search_service import search_kb
from services.system_setting_service import KEY_KB_SEARCH_HYBRID_ENABLED, invalidate_settings_cache, update_settings


def _vec(seed=0.5):
    return [seed] * OLLAMA_EMBED_DIM


@patch("services.kb_search_service.embed_text")
def test_debug_funnel_acl_isolation(mock_embed, db_session, regular_user, admin_user):
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    invalidate_settings_cache()
    mock_embed.return_value = _vec()

    secret_text = "acl_secret_token_xyz"
    f_owner = FileModel(
        filename="owner.pdf",
        original_name="owner.pdf",
        file_path="/tmp/owner",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    f_other = FileModel(
        filename="other.pdf",
        original_name="other.pdf",
        file_path="/tmp/other",
        file_size=1,
        mime_type="application/pdf",
        user_id=admin_user.id,
        index_status="ready",
    )
    db_session.add_all([f_owner, f_other])
    db_session.commit()
    for f, text in ((f_owner, secret_text), (f_other, "public content")):
        db_session.add(
            KbChunk(
                user_id=f.user_id,
                file_id=f.id,
                chunk_index=0,
                source="sidecar_md",
                text=text,
                char_start=0,
                char_end=len(text),
                embedding=_vec(0.9),
                embedding_model="test",
            )
        )
    db_session.commit()

    _, _, _, meta = search_kb(db_session, regular_user.id, secret_text, top_k=5, debug=True)
    funnel = meta.get("debug_funnel")
    assert funnel is not None
    assert funnel["after_acl_filter"] >= 1

    _, _, _, meta_other = search_kb(db_session, admin_user.id, secret_text, top_k=5, debug=True)
    funnel_other = meta_other.get("debug_funnel")
    assert funnel_other is not None
    assert funnel_other["after_acl_filter"] <= funnel["after_acl_filter"]


@patch("services.kb_search_service.embed_text")
def test_debug_funnel_absent_when_debug_false(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec()
    f = FileModel(
        filename="a.md",
        original_name="a.md",
        file_path="/tmp/a",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text="hello",
            char_start=0,
            char_end=5,
            embedding=_vec(0.1),
            embedding_model="test",
        )
    )
    db_session.commit()
    _, _, _, meta = search_kb(db_session, regular_user.id, "hello", top_k=5, debug=False)
    assert "debug_funnel" not in meta
