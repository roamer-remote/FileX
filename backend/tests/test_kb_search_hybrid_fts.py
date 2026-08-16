# Copyright (c) 2026 徐泽宇
"""007 US-02 AC3: hybrid=false must not invoke FTS (plainto_tsquery).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_search_service import search_kb
from services.system_setting_service import KEY_KB_SEARCH_HYBRID_ENABLED, update_settings


def _vec(seed: float) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


@patch("services.kb_search_service.embed_text")
def test_hybrid_false_skips_plainto_tsquery(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(0.9)
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "true"})

    f = FileModel(
        filename="a.md",
        original_name="发票说明.md",
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
            text="报销流程说明",
            char_start=0,
            char_end=6,
            embedding=_vec(0.5),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    with patch(
        "services.kb_search_service.func.plainto_tsquery",
        side_effect=AssertionError("FTS plainto_tsquery must not run when hybrid=false"),
    ):
        items, _, _, meta = search_kb(
            db_session,
            regular_user.id,
            "发票",
            top_k=5,
            hybrid=False,
            debug=True,
        )

    assert meta["effective_hybrid"] is False
    assert len(items) >= 1
