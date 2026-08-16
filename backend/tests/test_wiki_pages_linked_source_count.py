# Copyright (c) 2026 徐泽宇
"""主题页列表：linked_source_count 为引用该 slug 的 source 资料数。

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


def test_wiki_pages_linked_source_count(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    assert client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "Topic",
            "wiki_slug": "count-topic",
            "page_kind": "concept",
            "markdown": "# Topic\n",
        },
    ).status_code == 201

    a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "s1.txt", "a" * 32)
    b = _add_source(db_session, regular_user.id, ws_id, tmp_path, "s2.txt", "b" * 32)
    c = _add_source(db_session, regular_user.id, ws_id, tmp_path, "s3.txt", "c" * 32)

    for fid in (a.id, b.id, c.id):
        assert client.put(
            f"/api/files/{fid}/md",
            headers=h,
            json={"content": "[[wiki:count-topic]]\n"},
        ).status_code == 200

    pages = client.get("/api/knowledge-base/wiki/pages", headers=h).json()["items"]
    row = next(i for i in pages if i["wiki_slug"] == "count-topic")
    assert row["linked_source_count"] == 3


def test_wiki_page_linked_sources_list(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    assert client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "Topic",
            "wiki_slug": "list-topic",
            "page_kind": "concept",
            "markdown": "# Topic\n",
        },
    ).status_code == 201

    a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "la.txt", "d" * 32)
    b = _add_source(db_session, regular_user.id, ws_id, tmp_path, "lb.txt", "e" * 32)
    for fid in (a.id, b.id):
        assert client.put(
            f"/api/files/{fid}/md",
            headers=h,
            json={"content": "[[wiki:list-topic]]\n"},
        ).status_code == 200

    r = client.get(
        "/api/knowledge-base/wiki/pages/linked-sources",
        headers=h,
        params={"wiki_slug": "list-topic"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert {i["file_id"] for i in data["items"]} == {a.id, b.id}
