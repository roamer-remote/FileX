# Copyright (c) 2026 徐泽宇
"""Unit tests for search wiki_context_hint builder.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_search_wiki_hint import build_wiki_context_hint
from services.md_note_service import save_md_note_for_file
from services.workspace_service import ensure_personal_workspace


def _vec(seed: float = 0.5) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


def test_build_hint_no_outlinks(db_session, regular_user):
    personal = ensure_personal_workspace(db_session, regular_user)
    f = FileModel(
        user_id=regular_user.id,
        workspace_id=personal.id,
        filename="solo.txt",
        original_name="solo.txt",
        file_path="/tmp/solo",
        file_size=1,
        mime_type="text/plain",
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()

    hint = build_wiki_context_hint(db_session, regular_user, [f.id])
    assert hint is not None
    assert hint.required is False
    assert hint.expandable_seed_ids == []
    assert hint.recommended_parallel == 0
    assert hint.outlink_counts[f.id] == 0


def test_build_hint_with_outlinks(db_session, regular_user, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    a_path = tmp_path / "a.txt"
    b_path = tmp_path / "b.txt"
    a_path.write_text("x", encoding="utf-8")
    b_path.write_text("y", encoding="utf-8")
    a = FileModel(
        user_id=regular_user.id,
        workspace_id=personal.id,
        filename="a.txt",
        original_name="a.txt",
        file_path=str(a_path),
        file_size=1,
        mime_type="text/plain",
        index_status="ready",
    )
    b = FileModel(
        user_id=regular_user.id,
        workspace_id=personal.id,
        filename="b.txt",
        original_name="b.txt",
        file_path=str(b_path),
        file_size=1,
        mime_type="text/plain",
        index_status="ready",
    )
    db_session.add_all([a, b])
    db_session.commit()

    save_md_note_for_file(
        db_session,
        regular_user.id,
        a,
        f"link [[file:{b.id}]]\n",
        enqueue_vector_index=False,
    )
    db_session.commit()

    hint = build_wiki_context_hint(db_session, regular_user, [a.id, b.id])
    assert hint is not None
    assert hint.expandable_seed_ids == [a.id]
    assert hint.outlink_counts[a.id] == 1
    assert hint.outlink_counts[b.id] == 0
    assert hint.required is True
    assert hint.recommended_parallel == 1


def test_build_hint_two_expandable(db_session, regular_user, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    paths = [tmp_path / f"f{i}.txt" for i in range(3)]
    for p in paths:
        p.write_text("x", encoding="utf-8")
    files = []
    for i, p in enumerate(paths):
        files.append(
            FileModel(
                user_id=regular_user.id,
                workspace_id=personal.id,
                filename=p.name,
                original_name=p.name,
                file_path=str(p),
                file_size=1,
                mime_type="text/plain",
                index_status="ready",
            )
        )
    db_session.add_all(files)
    db_session.commit()
    a, b, c = files
    save_md_note_for_file(db_session, regular_user.id, a, f"[[file:{c.id}]]\n", enqueue_vector_index=False)
    save_md_note_for_file(db_session, regular_user.id, b, f"[[file:{c.id}]]\n", enqueue_vector_index=False)
    db_session.commit()

    hint = build_wiki_context_hint(db_session, regular_user, [a.id, b.id, c.id])
    assert hint.expandable_seed_ids == [a.id, b.id]
    assert hint.recommended_parallel == 2


@patch("services.kb_search_service.embed_text")
def test_search_hint_skips_appendix_when_no_outlinks(mock_embed, client, jwt_token, db_session, regular_user):
    mock_embed.return_value = _vec()
    f = FileModel(
        filename="a",
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
            text="freshness probe",
            char_start=0,
            char_end=15,
            embedding=_vec(0.1),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    r = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"query": "freshness", "top_k": 5},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    hint = data["wiki_context_hint"]
    assert hint is not None
    assert hint["expandable_seed_ids"] == []
    assert hint["required"] is False
    assert hint["recommended_parallel"] == 0
    assert "wiki-context" not in data["agent_notice"]
