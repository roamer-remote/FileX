# Copyright (c) 2026 徐泽宇
"""SC-047-001: owner PATCH chunk text 后 search 命中新文本。"""

from __future__ import annotations

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk


def _vec(seed: float = 0.91) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


PATCHED_MARKER = "SC047001_PATCHED_UNIQUE_PHRASE"


@patch("services.kb_search_service.embed_text")
@patch("services.kb_chunk_ops_service.resolve_embedding_vectors")
def test_sc047_001_owner_patch_then_search_hits_new_text(
    mock_patch_embed,
    mock_search_embed,
    client,
    db_session,
    regular_user,
    jwt_token,
):
    mock_patch_embed.return_value = [_vec(0.91)]
    mock_search_embed.return_value = _vec(0.91)

    f = FileModel(
        filename="a.bin",
        original_name="notes.md",
        file_path="/tmp/a",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
        chunk_count=1,
    )
    db_session.add(f)
    db_session.commit()
    ch = KbChunk(
        user_id=regular_user.id,
        file_id=f.id,
        chunk_index=0,
        source="sidecar_md",
        text="legacy chunk body before patch",
        char_start=0,
        char_end=30,
        embedding=_vec(0.2),
        embedding_model="test-model",
    )
    db_session.add(ch)
    db_session.commit()

    patch_resp = client.patch(
        f"/api/knowledge-base/files/{f.id}/chunks/{ch.id}",
        json={"text": f"intro {PATCHED_MARKER} tail", "reembed": True},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert PATCHED_MARKER in patch_resp.json()["text"]

    search_resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"query": PATCHED_MARKER, "top_k": 5, "hybrid": False},
    )
    assert search_resp.status_code == 200, search_resp.text
    items = search_resp.json()["items"]
    assert len(items) >= 1
    assert any(PATCHED_MARKER in (item.get("text") or "") for item in items)
    assert items[0]["file_id"] == f.id
