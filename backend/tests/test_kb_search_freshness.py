# Copyright (c) 2026 徐泽宇
"""Search response freshness: fetched_at and no-cache headers.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk


def _vec(seed: float = 0.5) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


@patch("services.kb_search_service.embed_text")
def test_search_response_fetched_at_and_no_cache(mock_embed, client, jwt_token, db_session, regular_user):
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
    assert data["fetched_at"].endswith("Z")
    assert "agent_notice" in data
    assert len(data["agent_notice"]) > 10
    assert "citation_label" in data["agent_notice"]
    assert data.get("wiki_context_hint") is not None
    assert f.id in data["wiki_context_hint"]["seed_file_ids"]
    cc = r.headers.get("cache-control", "").lower()
    assert "no-store" in cc
    assert r.headers.get("pragma") == "no-cache"


def test_get_file_has_no_cache_headers(client, jwt_token, db_session, regular_user):
    f = FileModel(
        filename="b",
        original_name="b.md",
        file_path="/tmp/b",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()

    r = client.get(
        f"/api/files/{f.id}",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "").lower()
