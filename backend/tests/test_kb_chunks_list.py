# Copyright (c) 2026 徐泽宇
"""GET /api/knowledge-base/files/{id}/chunks

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk


def _vec(seed: float) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


def test_list_chunks_for_own_file(client, db_session, regular_user, jwt_token):
    f = FileModel(
        filename="a",
        original_name="doc.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
        chunk_count=1,
        kb_index_manual_override=True,
    )
    db_session.add(f)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text="sample chunk text",
            char_start=0,
            char_end=18,
            embedding=_vec(0.2),
            embedding_model="test-model",
            loc_label="p.3",
            content_kind="paragraph",
        )
    )
    db_session.commit()

    r = client.get(
        f"/api/knowledge-base/files/{f.id}/chunks",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["text"] == "sample chunk text"
    assert body["items"][0]["embedding_preview"]["dim"] == OLLAMA_EMBED_DIM
    assert len(body["items"][0]["embedding_preview"]["head"]) == 12
    assert body["kb_index_manual_override"] is True
    assert body["items"][0]["loc_label"] == "p.3"


def test_list_chunks_404_other_user(client, db_session, regular_user, admin_user, jwt_token):
    f = FileModel(
        filename="b",
        original_name="secret.pdf",
        file_path="/tmp/b",
        file_size=1,
        mime_type="application/pdf",
        user_id=admin_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    r = client.get(
        f"/api/knowledge-base/files/{f.id}/chunks",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 404


def test_list_multimodal_figure_table_golden(client, db_session, regular_user, jwt_token):
    """SC-047-009: GET chunks 返回 figure/table content_kind + content_meta。"""
    f = FileModel(
        filename="m",
        original_name="report.pdf",
        file_path="/tmp/m",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
        chunk_count=2,
    )
    db_session.add(f)
    db_session.commit()
    db_session.add_all(
        [
            KbChunk(
                user_id=regular_user.id,
                file_id=f.id,
                chunk_index=0,
                source="sidecar_md",
                text="![fig](fig1.jpg)",
                char_start=0,
                char_end=16,
                embedding=_vec(0.1),
                embedding_model="test-model",
                content_kind="figure",
                content_meta={"page_idx": 1, "asset_key": "fig1.jpg", "caption": "示意图"},
                loc_label="p.2",
            ),
            KbChunk(
                user_id=regular_user.id,
                file_id=f.id,
                chunk_index=1,
                source="sidecar_md",
                text="| a | b |",
                char_start=20,
                char_end=27,
                embedding=_vec(0.2),
                embedding_model="test-model",
                content_kind="table",
                content_meta={"page_idx": 0, "caption": "销售汇总"},
                loc_label="p.1",
            ),
        ]
    )
    db_session.commit()

    r = client.get(
        f"/api/knowledge-base/files/{f.id}/chunks",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    figure = next(x for x in items if x["content_kind"] == "figure")
    table = next(x for x in items if x["content_kind"] == "table")
    assert figure["content_meta"]["asset_key"] == "fig1.jpg"
    assert figure["loc_label"] == "p.2"
    assert table["content_meta"]["caption"] == "销售汇总"
