# Copyright (c) 2026 徐泽宇
"""007 US-04 AC3: audit log stores original query when query_expansion is enabled.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_search_audit_log import KbSearchAuditLog


def _vec(seed: float) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


@patch("services.kb_search_service.embed_text")
def test_audit_log_query_is_original_not_expanded(mock_embed, client, jwt_token, db_session, regular_user):
    mock_embed.return_value = _vec(0.9)
    f = FileModel(
        filename="a",
        original_name="a.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
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
            text="报销流程",
            char_start=0,
            char_end=4,
            embedding=_vec(0.5),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    original_query = "发票"
    r = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": original_query,
            "top_k": 5,
            "query_expansion": True,
            "debug": True,
        },
    )
    assert r.status_code == 200, r.text
    meta = r.json().get("meta") or {}
    assert meta.get("query_expansion_enabled") is True
    assert "报销" in (meta.get("expanded_terms") or [])

    row = (
        db_session.query(KbSearchAuditLog)
        .filter(KbSearchAuditLog.user_id == regular_user.id)
        .order_by(KbSearchAuditLog.id.desc())
        .first()
    )
    assert row is not None
    assert row.query == original_query
    assert "报销" not in row.query
