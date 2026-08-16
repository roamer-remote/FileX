# Copyright (c) 2026 徐泽宇
"""017: POST /api/knowledge-base/wiki-context 多种子批量展开。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from services.workspace_service import ensure_personal_workspace


def _add_source(db_session, user_id, ws_id, tmp_path, name, md5, **extra):
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
        **extra,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_wiki_context_batch_dedupe_two_seeds(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "a.txt", "a" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "b.txt", "b" * 32)
    c = _add_source(db_session, regular_user.id, personal.id, tmp_path, "c.txt", "c" * 32)
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": "see [[file:" + str(b.id) + "]]\n"},
    )
    client.put(
        f"/api/files/{b.id}/md",
        headers=h,
        json={"content": "also [[file:" + str(c.id) + "]]\n"},
    )
    client.put(f"/api/files/{c.id}/md", headers=h, json={"content": "# c body\n"})
    r = client.post(
        "/api/knowledge-base/wiki-context",
        headers=h,
        json={"file_ids": [a.id, b.id], "depth": 1, "max_files": 8},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["seed_file_ids"] == [a.id, b.id]
    node_ids = [n["file_id"] for n in data["nodes"]]
    assert len(node_ids) == len(set(node_ids))
    assert a.id in node_ids and b.id in node_ids and c.id in node_ids


def test_wiki_context_batch_respects_global_max_files(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "s1.txt", "d" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "s2.txt", "e" * 32)
    t1 = _add_source(db_session, regular_user.id, personal.id, tmp_path, "t1.txt", "f" * 32)
    t2 = _add_source(db_session, regular_user.id, personal.id, tmp_path, "t2.txt", "0" * 32)
    client.put(f"/api/files/{a.id}/md", headers=h, json={"content": "[[file:" + str(t1.id) + "]]\n"})
    client.put(f"/api/files/{b.id}/md", headers=h, json={"content": "[[file:" + str(t2.id) + "]]\n"})
    client.put(f"/api/files/{t1.id}/md", headers=h, json={"content": "# t1\n"})
    client.put(f"/api/files/{t2.id}/md", headers=h, json={"content": "# t2\n"})
    data = client.post(
        "/api/knowledge-base/wiki-context",
        headers=h,
        json={"file_ids": [a.id, b.id], "max_files": 2},
    ).json()
    assert len(data["nodes"]) <= 2
    assert data["truncated"] is True


def test_wiki_context_batch_dedupes_input_file_ids(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "dup.txt", "g" * 32)
    client.put(f"/api/files/{a.id}/md", headers=h, json={"content": "# only seed\n"})
    data = client.post(
        "/api/knowledge-base/wiki-context",
        headers=h,
        json={"file_ids": [a.id, a.id], "max_files": 8},
    ).json()
    assert data["seed_file_ids"] == [a.id]
    assert len(data["nodes"]) == 1
