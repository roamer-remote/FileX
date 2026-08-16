# Copyright (c) 2026 徐泽宇
"""PATCH single KB chunk (047 T-2).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

import pytest

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_chunk_ops_service import patch_chunk


def _vec():
    return [0.1] * OLLAMA_EMBED_DIM


def _file_and_chunk(db_session, owner, *, index_source_hash="abc123"):
    f = FileModel(
        filename="a",
        original_name="a.md",
        file_path="/tmp/a",
        file_size=1,
        mime_type="text/markdown",
        user_id=owner.id,
        index_status="ready",
        index_source_hash=index_source_hash,
        kb_index_manual_override=False,
    )
    db_session.add(f)
    db_session.commit()
    ch = KbChunk(
        user_id=owner.id,
        file_id=f.id,
        chunk_index=0,
        source="sidecar_md",
        text="old",
        char_start=0,
        char_end=3,
        embedding=_vec(),
        embedding_model="test",
    )
    db_session.add(ch)
    db_session.commit()
    return f, ch


@patch("services.kb_embed_cache_service.embed_texts")
def test_patch_chunk_updates_text(mock_embed, db_session, regular_user):
    mock_embed.return_value = [_vec()]
    f, ch = _file_and_chunk(db_session, regular_user)
    updated = patch_chunk(db_session, regular_user, f.id, ch.id, text="new text", reembed=True)
    assert updated.text == "new text"
    mock_embed.assert_called_once()


@patch("services.kb_embed_cache_service.embed_texts")
def test_patch_text_sets_manual_override_preserves_hash(mock_embed, db_session, regular_user):
    mock_embed.return_value = [_vec()]
    f, ch = _file_and_chunk(db_session, regular_user, index_source_hash="keep-me")
    patch_chunk(db_session, regular_user, f.id, ch.id, text="edited", reembed=True)
    db_session.refresh(f)
    assert f.kb_index_manual_override is True
    assert f.index_source_hash == "keep-me"


@patch("services.kb_embed_cache_service.embed_texts")
def test_patch_keywords_only_leaves_override_false(mock_embed, db_session, regular_user):
    f, ch = _file_and_chunk(db_session, regular_user)
    patch_chunk(
        db_session,
        regular_user,
        f.id,
        ch.id,
        boost_keywords="foo, bar",
        reembed=False,
    )
    db_session.refresh(f)
    db_session.refresh(ch)
    assert ch.boost_keywords == "foo, bar"
    assert f.kb_index_manual_override is False
    mock_embed.assert_not_called()


@patch("services.kb_embed_cache_service.embed_texts")
def test_admin_patches_other_users_file(mock_embed, db_session, regular_user, admin_user):
    mock_embed.return_value = [_vec()]
    f, ch = _file_and_chunk(db_session, regular_user)
    updated = patch_chunk(db_session, admin_user, f.id, ch.id, text="admin edit", reembed=True)
    assert updated.text == "admin edit"
    db_session.refresh(f)
    assert f.kb_index_manual_override is True


def test_patch_chunk_not_found(db_session, regular_user):
    with pytest.raises(LookupError, match="file not found"):
        patch_chunk(db_session, regular_user, 99999, 1, text="x")
