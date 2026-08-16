# Copyright (c) 2026 徐泽宇
"""016 P0: provenance 字段 API 契约。

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


def test_wiki_links_provenance_file_direct_and_coref(
    client, db_session, regular_user, jwt_token, tmp_path
):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "prov_a.txt", "a" * 32)
    b = _add_source(db_session, regular_user.id, ws_id, tmp_path, "prov_b.txt", "b" * 32)

    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": f"[[file:{b.id}]]\n[[wiki:shared-prov]]\n"},
    )

    c = _add_source(db_session, regular_user.id, ws_id, tmp_path, "prov_c.txt", "c" * 32)
    client.put(
        f"/api/files/{c.id}/md",
        headers=h,
        json={"content": "[[wiki:shared-prov]]\n"},
    )

    data = client.get(f"/api/files/{a.id}/wiki-links", headers=h).json()
    file_out = next(o for o in data["outlinks"] if o.get("link_kind") == "file_id")
    assert file_out["provenance"] == "extracted"
    assert file_out["confidence"] == 1.0
    assert file_out["source_kind"] == "wiki_link"

    assert data["coref_count"] >= 1
    peer = data["coref_files"][0]
    assert peer["provenance"] == "inferred"
    assert peer["source_kind"] == "coref"
    assert peer["confidence"] >= 0.85


def test_link_graph_provenance_edge_types(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "lg_a.txt", "d" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "lg_b.txt", "e" * 32)
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": f"[[file:{b.id}]]\n"},
    )
    graph = client.get("/api/knowledge-base/link-graph", headers=h).json()
    direct = [e for e in graph["links"] if e["edge_type"] == "file_direct"][0]
    assert direct["provenance"] == "extracted"
    assert direct["confidence"] == 1.0


def test_wiki_context_node_provenance(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "ctx_a.txt", "f" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "ctx_b.txt", "0" * 32)
    client.put(f"/api/files/{a.id}/md", headers=h, json={"content": f"[[file:{b.id}]]\n"})
    client.put(f"/api/files/{b.id}/md", headers=h, json={"content": "# B\n"})

    resp = client.get(f"/api/files/{a.id}/wiki-context", headers=h).json()
    seed = next(n for n in resp["nodes"] if n["role"] == "seed")
    outlink = next(n for n in resp["nodes"] if n["role"] == "outlink")
    assert seed["provenance"] == "extracted"
    assert outlink["provenance"] == "extracted"
