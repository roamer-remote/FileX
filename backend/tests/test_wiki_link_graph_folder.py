# Copyright (c) 2026 徐泽宇
"""资料关系图按目录筛选。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from models.folder import Folder
from services.workspace_service import ensure_personal_workspace


def _add_file(db_session, user_id, workspace_id, *, folder_id, path, name, md5):
    f = FileModel(
        user_id=user_id,
        workspace_id=workspace_id,
        folder_id=folder_id,
        filename=name,
        original_name=name,
        file_path=str(path),
        file_size=1,
        mime_type="text/plain",
        md5_hash=md5,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_link_graph_folder_filter(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    folder_a = Folder(name="dir-a", parent_id=None, user_id=regular_user.id, workspace_id=ws_id)
    folder_b = Folder(name="dir-b", parent_id=None, user_id=regular_user.id, workspace_id=ws_id)
    db_session.add_all([folder_a, folder_b])
    db_session.commit()
    db_session.refresh(folder_a)
    db_session.refresh(folder_b)

    fa1 = _add_file(
        db_session,
        regular_user.id,
        ws_id,
        folder_id=folder_a.id,
        path=tmp_path / "a1.txt",
        name="a1.txt",
        md5="a" * 32,
    )
    fa2 = _add_file(
        db_session,
        regular_user.id,
        ws_id,
        folder_id=folder_a.id,
        path=tmp_path / "a2.txt",
        name="a2.txt",
        md5="b" * 32,
    )
    fb1 = _add_file(
        db_session,
        regular_user.id,
        ws_id,
        folder_id=folder_b.id,
        path=tmp_path / "b1.txt",
        name="b1.txt",
        md5="c" * 32,
    )

    r = client.put(
        f"/api/files/{fa1.id}/md",
        headers=h,
        json={"content": f"in A [[file:{fa2.id}]] and [[file:{fb1.id}]]\n"},
    )
    assert r.status_code == 200

    r_all = client.get("/api/knowledge-base/link-graph", headers=h)
    assert r_all.status_code == 200
    all_ids = {n["id"] for n in r_all.json()["nodes"]}
    assert fa1.id in all_ids and fa2.id in all_ids and fb1.id in all_ids

    r_a = client.get("/api/knowledge-base/link-graph", headers=h, params={"folder_id": folder_a.id})
    assert r_a.status_code == 200
    data_a = r_a.json()
    a_ids = {n["id"] for n in data_a["nodes"]}
    assert a_ids == {fa1.id, fa2.id}
    assert len(data_a["links"]) == 1
    assert data_a["links"][0]["source"] == fa1.id
    assert data_a["links"][0]["target"] == fa2.id

    r_missing = client.get("/api/knowledge-base/link-graph", headers=h, params={"folder_id": 999999})
    assert r_missing.status_code == 404
