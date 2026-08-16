# Copyright (c) 2026 徐泽宇
"""资料关系图：wiki slug 概念页与目录筛选。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from models.folder import Folder
from services.workspace_service import ensure_personal_workspace


def _add_file(db_session, user_id, workspace_id, *, folder_id, path, name, md5, **extra):
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
        **extra,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_link_graph_includes_wiki_slug_to_concept_outside_folder(
    client, db_session, regular_user, jwt_token, tmp_path
):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    hr = Folder(name="hr", parent_id=None, user_id=regular_user.id, workspace_id=ws_id)
    db_session.add(hr)
    db_session.commit()
    db_session.refresh(hr)

    resume = _add_file(
        db_session,
        regular_user.id,
        ws_id,
        folder_id=hr.id,
        path=tmp_path / "resume.txt",
        name="resume.txt",
        md5="a" * 32,
    )
    concept = _add_file(
        db_session,
        regular_user.id,
        ws_id,
        folder_id=None,
        path=tmp_path / "crispr.md",
        name="crispr.md",
        md5="b" * 32,
        page_kind="concept",
        wiki_slug="crispr-gene-editing",
    )

    r = client.put(
        f"/api/files/{resume.id}/md",
        headers=h,
        json={"content": "[[CRISPR|wiki:crispr-gene-editing]]\n"},
    )
    assert r.status_code == 200

    r_graph = client.get("/api/knowledge-base/link-graph", headers=h, params={"folder_id": hr.id})
    assert r_graph.status_code == 200
    data = r_graph.json()
    ids = {n["id"] for n in data["nodes"]}
    assert resume.id in ids
    assert concept.id in ids
    assert len(data["links"]) == 1
    link = data["links"][0]
    assert link["source"] == resume.id
    assert link["target"] == concept.id
    assert link["value"] == 1
    assert link["edge_type"] == "wiki_topic"
    assert link["wiki_slug"] == "crispr-gene-editing"


def test_resolve_wiki_slug_by_workspace_not_only_source_owner(
    client, db_session, regular_user, admin_user, jwt_token, admin_jwt_token, tmp_path
):
    from services.workspace_service import create_shared_workspace

    shared = create_shared_workspace(db_session, name="shared-wiki", owner=regular_user)
    h_admin = {"Authorization": f"Bearer {admin_jwt_token}"}
    h_user = {"Authorization": f"Bearer {jwt_token}"}

    src_path = tmp_path / "src.txt"
    src_path.write_text("x", encoding="utf-8")
    src = FileModel(
        user_id=regular_user.id,
        workspace_id=shared.id,
        filename="src.txt",
        original_name="src.txt",
        file_path=str(src_path),
        file_size=1,
        mime_type="text/plain",
        md5_hash="c" * 32,
        has_md=False,
    )
    db_session.add(src)
    db_session.commit()
    db_session.refresh(src)

    r = client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h_admin,
        json={
            "title": "VIP",
            "wiki_slug": "vip",
            "page_kind": "concept",
            "markdown": "# VIP\n",
            "workspace_id": shared.id,
        },
    )
    assert r.status_code == 201
    concept_id = r.json()["file"]["id"]

    r2 = client.put(
        f"/api/files/{src.id}/md",
        headers=h_user,
        params={"workspace_id": shared.id},
        json={"content": "[[重要人才|wiki:vip]]\n"},
    )
    assert r2.status_code == 200

    links = client.get(
        f"/api/files/{src.id}/wiki-links",
        headers=h_user,
        params={"workspace_id": shared.id},
    ).json()
    assert links["outlink_count"] == 1
    assert links["outlinks"][0]["target_file_id"] == concept_id
    assert links["outlinks"][0]["broken"] is False
