# Copyright (c) 2026 徐泽宇
"""标签共现图与热力矩阵统计。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from datetime import datetime, timezone

from models.file import File as FileModel
from services.tag_service import build_user_tag_graph, build_user_tag_heatmap, replace_file_tags


def test_build_user_tag_graph_cooccurrence(db_session, regular_user):
    base = datetime(2025, 3, 1, 8, 0, 0, tzinfo=timezone.utc)
    f_ab = FileModel(
        user_id=regular_user.id,
        filename="ab.bin",
        original_name="ab.txt",
        file_path="/tmp/ab",
        file_size=1,
        mime_type="text/plain",
        md5_hash="a" * 32,
        has_md=False,
        created_at=base,
        updated_at=base,
    )
    f_a = FileModel(
        user_id=regular_user.id,
        filename="a.bin",
        original_name="a.txt",
        file_path="/tmp/a",
        file_size=1,
        mime_type="text/plain",
        md5_hash="b" * 32,
        has_md=False,
        created_at=base,
        updated_at=base,
    )
    db_session.add_all([f_ab, f_a])
    db_session.commit()
    db_session.refresh(f_ab)
    db_session.refresh(f_a)

    replace_file_tags(db_session, regular_user.id, f_ab.id, ["alpha", "beta"])
    replace_file_tags(db_session, regular_user.id, f_a.id, ["alpha"])
    db_session.commit()

    graph = build_user_tag_graph(db_session, regular_user.id)
    nodes = {n["name"]: n["value"] for n in graph["nodes"]}
    assert nodes["alpha"] == 2
    assert nodes["beta"] == 1
    assert graph["total_files_with_tags"] == 2
    assert len(graph["file_groups"]) == 2
    assert graph["truncated"] is False
    link = next(l for l in graph["links"] if {l["source"], l["target"]} == {"alpha", "beta"})
    assert link["value"] == 1

    heat = build_user_tag_heatmap(db_session, regular_user.id)
    assert heat["tags"] == ["alpha", "beta"]
    ia, ib = 0, 1
    assert heat["matrix"][ia][ia] == 2
    assert heat["matrix"][ib][ib] == 1
    assert heat["matrix"][ia][ib] == 1
    assert heat["matrix"][ib][ia] == 1


def test_get_tags_graph_api(client, db_session, regular_user, jwt_token):
    base = datetime(2025, 3, 2, 8, 0, 0, tzinfo=timezone.utc)
    f1 = FileModel(
        user_id=regular_user.id,
        filename="t.bin",
        original_name="t.txt",
        file_path="/tmp/t",
        file_size=1,
        mime_type="text/plain",
        md5_hash="c" * 32,
        has_md=False,
        created_at=base,
        updated_at=base,
    )
    db_session.add(f1)
    db_session.commit()
    db_session.refresh(f1)
    replace_file_tags(db_session, regular_user.id, f1.id, ["solo"])
    db_session.commit()

    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.get("/api/files/tags/graph", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(n["name"] == "solo" and n["value"] == 1 for n in body["nodes"])

    r2 = client.get("/api/files/tags/heatmap", headers=h)
    assert r2.status_code == 200, r2.text
    assert r2.json()["tags"] == ["solo"]

def test_build_user_tag_graph_file_limit_and_shared_tag(db_session, regular_user):
    base = datetime(2025, 3, 1, 8, 0, 0, tzinfo=timezone.utc)
    f_old = FileModel(
        user_id=regular_user.id,
        filename="old.bin",
        original_name="old.txt",
        file_path="/tmp/old",
        file_size=1,
        mime_type="text/plain",
        md5_hash="d" * 32,
        has_md=False,
        created_at=base,
        updated_at=base,
    )
    f_mid = FileModel(
        user_id=regular_user.id,
        filename="mid.bin",
        original_name="mid.txt",
        file_path="/tmp/mid",
        file_size=1,
        mime_type="text/plain",
        md5_hash="e" * 32,
        has_md=False,
        created_at=base,
        updated_at=datetime(2025, 3, 2, 8, 0, 0, tzinfo=timezone.utc),
    )
    f_new = FileModel(
        user_id=regular_user.id,
        filename="new.bin",
        original_name="new.txt",
        file_path="/tmp/new",
        file_size=1,
        mime_type="text/plain",
        md5_hash="f" * 32,
        has_md=False,
        created_at=base,
        updated_at=datetime(2025, 3, 3, 8, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([f_old, f_mid, f_new])
    db_session.commit()
    for f in (f_old, f_mid, f_new):
        db_session.refresh(f)

    replace_file_tags(db_session, regular_user.id, f_old.id, ["shared", "only-old"])
    replace_file_tags(db_session, regular_user.id, f_mid.id, ["shared", "only-mid"])
    replace_file_tags(db_session, regular_user.id, f_new.id, ["shared", "only-new"])
    f_old.updated_at = base
    f_mid.updated_at = datetime(2025, 3, 2, 8, 0, 0, tzinfo=timezone.utc)
    f_new.updated_at = datetime(2025, 3, 3, 8, 0, 0, tzinfo=timezone.utc)
    db_session.commit()

    graph = build_user_tag_graph(db_session, regular_user.id, file_limit=2)
    assert graph["truncated"] is True
    assert graph["total_files_with_tags"] == 3
    assert len(graph["file_groups"]) == 2
    shown_ids = {g["file_id"] for g in graph["file_groups"]}
    assert f_new.id in shown_ids
    assert f_mid.id in shown_ids
    assert f_old.id not in shown_ids

    names = {n["name"] for n in graph["nodes"]}
    assert names == {"shared", "only-mid", "only-new"}

    shared_nodes = [n for n in graph["nodes"] if n["name"] == "shared"]
    assert len(shared_nodes) == 1
    assert shared_nodes[0]["value"] == 3

    link_keys = {(l["source"], l["target"]) if l["source"] < l["target"] else (l["target"], l["source"]) for l in graph["links"]}
    assert ("only-mid", "shared") in link_keys
    assert ("only-new", "shared") in link_keys


def test_build_user_tag_heatmap_caps_large_tag_sets(db_session, regular_user):
    from models.file import File as FileModel
    from services.workspace_service import ensure_personal_workspace
    from services.tag_service import build_user_tag_heatmap, replace_file_tags

    ws = ensure_personal_workspace(db_session, regular_user)
    f = FileModel(
        user_id=regular_user.id,
        workspace_id=ws.id,
        filename="many-tags.txt",
        original_name="many-tags.txt",
        file_path="/tmp/many-tags.txt",
        file_size=1,
        mime_type="text/plain",
        md5_hash="e" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    replace_file_tags(db_session, regular_user.id, f.id, [f"tag-{i:03d}" for i in range(90)])
    db_session.commit()

    heatmap = build_user_tag_heatmap(db_session, regular_user.id, max_tags=80)

    assert heatmap["truncated"] is True
    assert heatmap["total_tags"] == 90
    assert len(heatmap["tags"]) == 80
    assert len(heatmap["matrix"]) == 80
    assert all(len(row) == 80 for row in heatmap["matrix"])
