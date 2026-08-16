# Copyright (c) 2026 徐泽宇
"""012: Wiki 共引边与 link-graph 分边类型。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from models.file_wiki_link import FileWikiLink
from services.workspace_service import ensure_personal_workspace


def _add_source(db_session, user_id, ws_id, tmp_path, name, md5, **extra):
    p = tmp_path / name
    p.write_text("x", encoding="utf-8")
    page_kind = extra.pop("page_kind", "source")
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
        page_kind=page_kind,
        **extra,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def test_coref_without_concept_page(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "a.txt", "a" * 32)
    b = _add_source(db_session, regular_user.id, ws_id, tmp_path, "b.txt", "b" * 32)

    for fid in (a.id, b.id):
        r = client.put(
            f"/api/files/{fid}/md",
            headers=h,
            json={"content": "[[wiki:shared-topic]]\n"},
        )
        assert r.status_code == 200

    graph = client.get("/api/knowledge-base/link-graph", headers=h).json()
    coref = [e for e in graph["links"] if e.get("edge_type") == "wiki_coref"]
    topic = [e for e in graph["links"] if e.get("edge_type") == "wiki_topic"]
    assert len(coref) == 1
    assert {coref[0]["source"], coref[0]["target"]} == {a.id, b.id}
    assert coref[0]["wiki_slug"] == "shared-topic"
    assert topic == []
    hub_nodes = [n for n in graph["nodes"] if n.get("page_kind") != "source"]
    assert hub_nodes == []


def test_coref_and_topic_with_concept_page(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "pa.txt", "c" * 32)
    b = _add_source(db_session, regular_user.id, ws_id, tmp_path, "pb.txt", "d" * 32)

    r = client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "Topic",
            "wiki_slug": "dual-topic",
            "page_kind": "concept",
            "markdown": "# Topic\n",
        },
    )
    assert r.status_code == 201
    concept_id = r.json()["file"]["id"]

    for fid in (a.id, b.id):
        assert client.put(
            f"/api/files/{fid}/md",
            headers=h,
            json={"content": "[[wiki:dual-topic]]\n"},
        ).status_code == 200

    graph = client.get("/api/knowledge-base/link-graph", headers=h).json()
    coref = [e for e in graph["links"] if e["edge_type"] == "wiki_coref"]
    topic = [e for e in graph["links"] if e["edge_type"] == "wiki_topic"]
    assert len(coref) == 1
    assert len(topic) == 2
    assert all(e["target"] == concept_id for e in topic)


def test_link_graph_topic_edges_include_stale_slug_links(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    ws_id = personal.id
    h = {"Authorization": f"Bearer {jwt_token}"}

    topic = _add_source(
        db_session,
        regular_user.id,
        ws_id,
        tmp_path,
        "topic.md",
        "1" * 32,
        page_kind="concept",
        wiki_slug="stale-topic",
    )
    resolved = _add_source(db_session, regular_user.id, ws_id, tmp_path, "photo.png", "2" * 32)
    stale_a = _add_source(db_session, regular_user.id, ws_id, tmp_path, "resume-a.doc", "3" * 32)
    stale_b = _add_source(db_session, regular_user.id, ws_id, tmp_path, "resume-b.doc", "4" * 32)

    db_session.add_all(
        [
            FileWikiLink(
                source_file_id=resolved.id,
                target_file_id=topic.id,
                target_wiki_slug="stale-topic",
                link_kind="wiki_slug",
                occurrence_index=1,
                anchor_id="resolved-stale-topic",
                start_offset=0,
                end_offset=20,
            ),
            FileWikiLink(
                source_file_id=stale_a.id,
                target_file_id=None,
                target_wiki_slug="stale-topic",
                link_kind="wiki_slug",
                occurrence_index=1,
                anchor_id="resume-a-stale-topic",
                start_offset=0,
                end_offset=20,
                broken_reason="deleted",
            ),
            FileWikiLink(
                source_file_id=stale_b.id,
                target_file_id=None,
                target_wiki_slug="stale-topic",
                link_kind="wiki_slug",
                occurrence_index=1,
                anchor_id="resume-b-stale-topic",
                start_offset=0,
                end_offset=20,
                broken_reason="deleted",
            ),
        ]
    )
    db_session.commit()

    graph = client.get("/api/knowledge-base/link-graph", headers=h).json()
    topic_edges = [
        e
        for e in graph["links"]
        if e.get("edge_type") == "wiki_topic" and e.get("target") == topic.id
    ]
    assert {e["source"] for e in topic_edges} == {resolved.id, stale_a.id, stale_b.id}


def test_single_slug_no_coref(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(
        db_session,
        regular_user.id,
        personal.id,
        tmp_path,
        "solo.txt",
        "e" * 32,
    )
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": "[[wiki:lonely]]\n"},
    )
    graph = client.get("/api/knowledge-base/link-graph", headers=h).json()
    assert not any(e.get("edge_type") == "wiki_coref" for e in graph["links"])


def test_file_direct_edge_type(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "src.txt", "f" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "tgt.txt", "0" * 32)
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": f"[[file:{b.id}]]\n"},
    )
    graph = client.get("/api/knowledge-base/link-graph", headers=h).json()
    direct = [e for e in graph["links"] if e["edge_type"] == "file_direct"]
    assert len(direct) == 1
    assert direct[0]["source"] == a.id
    assert direct[0]["target"] == b.id


def test_wiki_links_coref_files(client, db_session, regular_user, jwt_token, tmp_path):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "x1.txt", "1" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "x2.txt", "2" * 32)
    for fid in (a.id, b.id):
        client.put(
            f"/api/files/{fid}/md",
            headers=h,
            json={"content": "[[wiki:peer-slug]]\n"},
        )
    data = client.get(f"/api/files/{a.id}/wiki-links", headers=h).json()
    assert data["coref_count"] == 1
    assert data["coref_files"][0]["file_id"] == b.id
    assert data["coref_files"][0]["shared_wiki_slugs"] == ["peer-slug"]
