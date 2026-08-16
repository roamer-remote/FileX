# Copyright (c) 2026 徐泽宇
"""014: GET /api/files/{id}/wiki-context Wiki 邻居 MD 展开。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from services.workspace_service import ensure_personal_workspace
from tests.conftest import _create_user


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


def test_wiki_context_file_outlink(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "a.txt", "a" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "b.txt", "b" * 32)
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": f"see [[file:{b.id}]]\n"},
    )
    client.put(
        f"/api/files/{b.id}/md",
        headers=h,
        json={"content": "# target body\n"},
    )
    r = client.get(f"/api/files/{a.id}/wiki-context", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["seed_file_id"] == a.id
    assert data["truncated"] is False
    roles = {n["file_id"]: n["role"] for n in data["nodes"]}
    assert roles[a.id] == "seed"
    assert roles[b.id] == "outlink"
    b_node = next(n for n in data["nodes"] if n["file_id"] == b.id)
    assert "target body" in b_node["markdown"]
    assert b_node["link_from"]["file_id"] == a.id
    assert b_node["link_from"]["link_kind"] == "file_id"


def test_wiki_context_wiki_topic_page(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    src = _add_source(db_session, regular_user.id, personal.id, tmp_path, "src.txt", "c" * 32)
    r = client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "Topic",
            "wiki_slug": "ctx-topic",
            "page_kind": "concept",
            "markdown": "# Topic hub\n",
        },
    )
    assert r.status_code == 201
    topic_id = r.json()["file"]["id"]
    client.put(
        f"/api/files/{src.id}/md",
        headers=h,
        json={"content": "[[wiki:ctx-topic]]\n"},
    )
    data = client.get(f"/api/files/{src.id}/wiki-context", headers=h).json()
    topic_node = next(n for n in data["nodes"] if n["file_id"] == topic_id)
    assert topic_node["page_kind"] == "concept"
    assert topic_node["role"] == "outlink"
    assert "Topic hub" in topic_node["markdown"]


def test_wiki_context_broken_wiki_skipped(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    src = _add_source(db_session, regular_user.id, personal.id, tmp_path, "broken.txt", "d" * 32)
    client.put(
        f"/api/files/{src.id}/md",
        headers=h,
        json={"content": "[[wiki:missing-slug]]\n"},
    )
    data = client.get(f"/api/files/{src.id}/wiki-context", headers=h).json()
    assert len(data["nodes"]) == 1
    assert any(s.get("wiki_slug") == "missing-slug" for s in data["skipped"])


def test_wiki_context_max_files_truncated(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "root.txt", "e" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "t1.txt", "f" * 32)
    c = _add_source(db_session, regular_user.id, personal.id, tmp_path, "t2.txt", "0" * 32)
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": f"[[file:{b.id}]] [[file:{c.id}]]\n"},
    )
    data = client.get(
        f"/api/files/{a.id}/wiki-context?max_files=2",
        headers=h,
    ).json()
    assert len(data["nodes"]) <= 2
    assert data["truncated"] is True


def test_wiki_context_max_files_one_seed_only(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "solo.txt", "1" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "peer.txt", "2" * 32)
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": f"[[file:{b.id}]]\n"},
    )
    data = client.get(
        f"/api/files/{a.id}/wiki-context?max_files=1",
        headers=h,
    ).json()
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["role"] == "seed"
    assert data["truncated"] is False


def test_wiki_context_include_coref(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "x1.txt", "3" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "x2.txt", "4" * 32)
    for fid in (a.id, b.id):
        client.put(
            f"/api/files/{fid}/md",
            headers=h,
            json={"content": "[[wiki:shared-ctx]] peer\n"},
        )
    data = client.get(
        f"/api/files/{a.id}/wiki-context?include_coref=true",
        headers=h,
    ).json()
    roles = {n["file_id"]: n["role"] for n in data["nodes"]}
    assert roles[a.id] == "seed"
    assert roles.get(b.id) == "coref"


def test_wiki_context_no_md_target(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "linker.txt", "5" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "nomd.txt", "6" * 32)
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": f"[[file:{b.id}]]\n"},
    )
    data = client.get(f"/api/files/{a.id}/wiki-context", headers=h).json()
    b_node = next(n for n in data["nodes"] if n["file_id"] == b.id)
    assert b_node["has_md"] is False
    assert b_node["markdown"] == ""

def test_wiki_context_acl_hides_inaccessible_outlink(
    client, db_session, regular_user, jwt_token, tmp_path
):
    """SC-003：出链目标属其他用户个人空间时不可见。"""
    personal = ensure_personal_workspace(db_session, regular_user)
    other = _create_user(db_session, "wiki_ctx_other")
    other_ws = ensure_personal_workspace(db_session, other)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "a.txt", "7" * 32)
    b = _add_source(db_session, other.id, other_ws.id, tmp_path, "b.txt", "8" * 32)
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": f"see [[file:{b.id}]]\n"},
    )
    data = client.get(f"/api/files/{a.id}/wiki-context", headers=h).json()
    node_ids = [n["file_id"] for n in data["nodes"]]
    assert a.id in node_ids
    assert b.id not in node_ids

