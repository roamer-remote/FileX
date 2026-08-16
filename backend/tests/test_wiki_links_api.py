# Copyright (c) 2026 徐泽宇
"""wiki links api 相关测试模块。

Authors:
    徐泽宇
"""

from unittest.mock import patch

from models.file import File as FileModel
from models.file_wiki_link import FileWikiLink
from services.workspace_service import ensure_personal_workspace


def test_put_md_creates_wiki_links(client, db_session, regular_user, jwt_token, tmp_path):
    p = tmp_path / "d.bin"
    p.write_text("x", encoding="utf-8")
    f = FileModel(
        user_id=regular_user.id,
        filename="d.bin",
        original_name="d.bin",
        file_path=str(p),
        file_size=1,
        mime_type="application/octet-stream",
        md5_hash="a" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)

    p2 = tmp_path / "t.bin"
    p2.write_text("y", encoding="utf-8")
    t = FileModel(
        user_id=regular_user.id,
        filename="t.bin",
        original_name="t.bin",
        file_path=str(p2),
        file_size=1,
        mime_type="application/octet-stream",
        md5_hash="b" * 32,
        has_md=False,
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    h = {"Authorization": f"Bearer {jwt_token}"}
    r = client.put(
        f"/api/files/{f.id}/md",
        headers=h,
        json={"content": f"link [[file:{t.id}]] and [[wiki:missing]]\n"},
    )
    assert r.status_code == 200

    r2 = client.get(f"/api/files/{f.id}/wiki-links", headers=h)
    assert r2.status_code == 200
    data = r2.json()
    assert data["outlink_count"] == 2
    hit = next(o for o in data["outlinks"] if o["target_file_id"] == t.id and not o["broken"])
    assert hit.get("target_name") == "t.bin"
    assert isinstance(hit.get("start_offset"), int)
    assert isinstance(hit.get("end_offset"), int)
    assert hit["end_offset"] > hit["start_offset"]
    assert any(o["broken_reason"] == "deleted" for o in data["outlinks"])

    r3 = client.get(f"/api/files/{t.id}/wiki-links", headers=h)
    assert r3.json()["backlink_count"] == 1


@patch("services.kb_index_service.enqueue_index")
def test_wiki_page_heals_slug_links(mock_enqueue, client, db_session, regular_user, jwt_token, tmp_path):
    mock_enqueue.return_value = None
    p = tmp_path / "s.bin"
    p.write_text("x", encoding="utf-8")
    f = FileModel(
        user_id=regular_user.id,
        filename="s.bin",
        original_name="s.bin",
        file_path=str(p),
        file_size=1,
        mime_type="application/octet-stream",
        md5_hash="c" * 32,
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    h = {"Authorization": f"Bearer {jwt_token}"}
    client.put(f"/api/files/{f.id}/md", headers=h, json={"content": "[[wiki:heal-me]]\n"})

    r = client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "Heal",
            "wiki_slug": "heal-me",
            "page_kind": "concept",
            "markdown": "# Heal\n",
        },
    )
    assert r.status_code == 201

    r2 = client.get(f"/api/files/{f.id}/wiki-links", headers=h)
    out = r2.json()["outlinks"]
    assert len(out) == 1
    assert out[0]["broken_reason"] is None
    assert out[0]["target_file_id"] is not None


def test_wiki_links_dedupe_by_target_and_source(client, db_session, regular_user, jwt_token, tmp_path):
    h = {"Authorization": f"Bearer {jwt_token}"}

    def _file(name: str, md5: str) -> FileModel:
        path = tmp_path / name
        path.write_text("x", encoding="utf-8")
        rec = FileModel(
            user_id=regular_user.id,
            filename=name,
            original_name=name,
            file_path=str(path),
            file_size=1,
            mime_type="application/octet-stream",
            md5_hash=md5,
            has_md=False,
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)
        return rec

    src = _file("src.bin", "d" * 32)
    tgt = _file("tgt.bin", "e" * 32)
    r = client.put(
        f"/api/files/{src.id}/md",
        headers=h,
        json={"content": f"[[file:{tgt.id}]] and again [[file:{tgt.id}]]\n"},
    )
    assert r.status_code == 200
    data = client.get(f"/api/files/{src.id}/wiki-links", headers=h).json()
    assert data["outlink_count"] == 1
    assert len(data["outlinks"]) == 1

    client.put(
        f"/api/files/{tgt.id}/md",
        headers=h,
        json={"content": f"back [[file:{src.id}]] twice [[file:{src.id}]]\n"},
    )
    back = client.get(f"/api/files/{src.id}/wiki-links", headers=h).json()
    assert back["backlink_count"] == 1
    assert len(back["backlinks"]) == 1

    raw_out = client.get(f"/api/files/{src.id}/wiki-links?dedupe=false", headers=h).json()
    assert raw_out["outlink_count"] == 2
    assert len(raw_out["outlinks"]) == 2

    raw_back = client.get(f"/api/files/{tgt.id}/wiki-links?dedupe=false", headers=h).json()
    assert raw_back["backlink_count"] == 2
    assert len(raw_back["backlinks"]) == 2


def test_wiki_page_backlinks_include_stale_slug_links(client, db_session, regular_user, jwt_token, tmp_path):
    h = {"Authorization": f"Bearer {jwt_token}"}
    workspace_id = ensure_personal_workspace(db_session, regular_user).id

    def _file(name: str, md5: str, *, page_kind: str = "source", wiki_slug: str | None = None) -> FileModel:
        path = tmp_path / name
        path.write_text("x", encoding="utf-8")
        rec = FileModel(
            user_id=regular_user.id,
            filename=name,
            original_name=name,
            file_path=str(path),
            file_size=1,
            mime_type="text/markdown",
            md5_hash=md5,
            has_md=False,
            page_kind=page_kind,
            wiki_slug=wiki_slug,
            workspace_id=workspace_id,
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)
        return rec

    topic = _file("北斗协作.md", "f" * 32, page_kind="concept", wiki_slug="北斗协作")
    resolved = _file("resolved.md", "1" * 32)
    stale_a = _file("邓良玉简历.md", "2" * 32, page_kind="concept")
    stale_b = _file("徐泽宇简历.md", "3" * 32, page_kind="concept")

    db_session.add_all(
        [
            FileWikiLink(
                source_file_id=resolved.id,
                target_file_id=topic.id,
                target_wiki_slug="北斗协作",
                link_kind="wiki_slug",
                occurrence_index=1,
                anchor_id="resolved-topic",
                start_offset=0,
                end_offset=13,
            ),
            FileWikiLink(
                source_file_id=stale_a.id,
                target_file_id=None,
                target_wiki_slug="北斗协作",
                link_kind="wiki_slug",
                occurrence_index=1,
                anchor_id="stale-a-topic",
                start_offset=0,
                end_offset=13,
                broken_reason="deleted",
            ),
            FileWikiLink(
                source_file_id=stale_b.id,
                target_file_id=None,
                target_wiki_slug="北斗协作",
                link_kind="wiki_slug",
                occurrence_index=1,
                anchor_id="stale-b-topic",
                start_offset=0,
                end_offset=13,
                broken_reason="deleted",
            ),
        ]
    )
    db_session.commit()

    data = client.get(f"/api/files/{topic.id}/wiki-links", headers=h).json()
    assert data["backlink_count"] == 3
    assert {row["source_file_id"] for row in data["backlinks"]} == {
        resolved.id,
        stale_a.id,
        stale_b.id,
    }
