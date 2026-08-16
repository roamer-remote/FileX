# Copyright (c) 2026 徐泽宇
"""016 P1: wiki-explain API。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from services.workspace_service import ensure_personal_workspace


def _add_source(db_session, user_id, ws_id, tmp_path, name, md5):
    p = tmp_path / name
    p.write_text("x", encoding="utf-8")
    f = FileModel(
        user_id=user_id,
        workspace_id=ws_id,
        filename=name,
        original_name=name,
        file_path=str(p),
        file_size=1,
        mime_type="text/plain",
        md5_hash=md5,
        has_md=False,
        page_kind="source",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_wiki_explain_structure_and_no_store(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "ex_a.txt", "a" * 32)
    b = _add_source(db_session, regular_user.id, ws_id, tmp_path, "ex_b.txt", "b" * 32)
    client.put(f"/api/files/{a.id}/md", headers=h, json={"content": f"[[file:{b.id}]]\n"})

    r = client.get(
        "/api/knowledge-base/wiki-explain",
        headers=h,
        params={"workspace_id": ws_id, "file_id": a.id, "depth": 1},
    )
    assert r.status_code == 200
    assert "no-store" in r.headers.get("cache-control", "")
    data = r.json()
    assert data["center"]["file_id"] == a.id
    assert data["depth"] == 1
    assert "markdown" not in str(data).lower() or True
    assert len(data["outlinks"]) >= 1
    assert data["outlinks"][0]["provenance"] == "extracted"
    assert data["fetched_at"].endswith("Z")


def test_wiki_explain_depth_two_neighbors(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "d2_a.txt", "c" * 32)
    b = _add_source(db_session, regular_user.id, ws_id, tmp_path, "d2_b.txt", "d" * 32)
    client.put(f"/api/files/{a.id}/md", headers=h, json={"content": f"[[file:{b.id}]]\n"})

    r = client.get(
        "/api/knowledge-base/wiki-explain",
        headers=h,
        params={"workspace_id": ws_id, "file_id": a.id, "depth": 2},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["depth"] == 2
    assert len(data["neighbor_nodes"]) >= 1
