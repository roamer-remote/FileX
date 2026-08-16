# Copyright (c) 2026 徐泽宇
"""016 P1: wiki-path API。

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


def test_wiki_path_direct_one_hop(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "path_a.txt", "a" * 32)
    b = _add_source(db_session, regular_user.id, ws_id, tmp_path, "path_b.txt", "b" * 32)
    client.put(f"/api/files/{a.id}/md", headers=h, json={"content": f"[[file:{b.id}]]\n"})

    r = client.get(
        "/api/knowledge-base/wiki-path",
        headers=h,
        params={
            "workspace_id": ws_id,
            "from_file_id": a.id,
            "to_file_id": b.id,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["found"] is True
    assert data["hops"] == 1
    assert "no-store" in r.headers.get("cache-control", "")


def test_wiki_path_coref_two_files(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "pc_a.txt", "c" * 32)
    b = _add_source(db_session, regular_user.id, ws_id, tmp_path, "pc_b.txt", "d" * 32)
    for fid in (a.id, b.id):
        client.put(
            f"/api/files/{fid}/md",
            headers=h,
            json={"content": "[[wiki:path-shared]]\n"},
        )

    r = client.get(
        "/api/knowledge-base/wiki-path",
        headers=h,
        params={
            "workspace_id": ws_id,
            "from_file_id": a.id,
            "to_file_id": b.id,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["found"] is True
    assert data["hops"] == 1
    hub = [p for p in data["path"] if p.get("node_type") == "wiki_hub"]
    assert hub and hub[0]["slug"] == "path-shared"


def test_wiki_path_not_found(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "iso_a.txt", "e" * 32)
    b = _add_source(db_session, regular_user.id, ws_id, tmp_path, "iso_b.txt", "f" * 32)

    r = client.get(
        "/api/knowledge-base/wiki-path",
        headers=h,
        params={
            "workspace_id": ws_id,
            "from_file_id": a.id,
            "to_file_id": b.id,
        },
    )
    assert r.status_code == 200
    assert r.json()["found"] is False


def test_wiki_path_slug_not_found(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "slug_a.txt", "1" * 32)

    r = client.get(
        "/api/knowledge-base/wiki-path",
        headers=h,
        params={
            "workspace_id": ws_id,
            "from_file_id": a.id,
            "to_slug": "missing-slug-xyz",
        },
    )
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail.get("not_found") == "slug"
