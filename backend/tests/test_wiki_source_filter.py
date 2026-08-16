# Copyright (c) 2026 徐泽宇
"""Wiki 主题页不出现在资料视图（list / AUTO / stats）；仍可按 id 访问。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

from models.file import File as FileModel
from models.file_wiki_link import FileWikiLink
from services.file_stats_service import get_user_file_stats
from services.knowledge_base_index_service import render_auto_section, render_wiki_section


@patch("services.kb_index_service.enqueue_index")
def test_list_files_excludes_wiki_theme_pages(mock_enqueue, client, db_session, regular_user, jwt_token):
    mock_enqueue.return_value = None
    h = {"Authorization": f"Bearer {jwt_token}"}

    src = client.post(
        "/api/files/upload",
        headers=h,
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert src.status_code == 200, src.text
    source_id = src.json()["id"]

    wiki = client.post(
        "/api/knowledge-base/wiki/pages",
        headers=h,
        json={
            "title": "Filter Test",
            "wiki_slug": "filter-test",
            "page_kind": "concept",
            "markdown": "# Filter\n",
        },
    )
    assert wiki.status_code == 201, wiki.text
    wiki_file_id = wiki.json()["file"]["id"]

    listed = client.get("/api/files", headers=h)
    assert listed.status_code == 200
    ids = {x["id"] for x in listed.json()["items"]}
    assert source_id in ids
    assert wiki_file_id not in ids

    by_id = client.get(f"/api/files/{wiki_file_id}", headers=h)
    assert by_id.status_code == 200
    assert by_id.json()["wiki_slug"] == "filter-test"


@patch("services.kb_index_service.enqueue_index")
def test_render_auto_section_excludes_wiki_pages(mock_enqueue, db_session, regular_user):
    mock_enqueue.return_value = None

    src = FileModel(
        user_id=regular_user.id,
        filename="s.bin",
        original_name="source.txt",
        file_path="/tmp/s",
        file_size=1,
        mime_type="text/plain",
        md5_hash="c" * 32,
        page_kind="source",
    )
    wiki = FileModel(
        user_id=regular_user.id,
        filename="w.bin",
        original_name="topic.md",
        file_path="/tmp/w",
        file_size=1,
        mime_type="text/markdown",
        md5_hash="d" * 32,
        page_kind="concept",
        wiki_slug="auto-filter-test",
        has_md=True,
    )
    db_session.add_all([src, wiki])
    db_session.commit()

    auto = render_auto_section(db_session, regular_user.id)
    wiki_sec = render_wiki_section(db_session, regular_user.id)

    assert str(src.id) in auto
    assert str(wiki.id) not in auto
    assert str(wiki.id) not in wiki_sec
    assert str(src.id) not in wiki_sec


def test_render_wiki_section_includes_linked_source_only(db_session, regular_user):
    src = FileModel(
        user_id=regular_user.id,
        filename="linked.bin",
        original_name="linked.pdf",
        file_path="/tmp/linked",
        file_size=1,
        mime_type="application/pdf",
        md5_hash="f" * 32,
        page_kind="source",
        has_md=True,
    )
    target = FileModel(
        user_id=regular_user.id,
        filename="topic.bin",
        original_name="topic.md",
        file_path="/tmp/topic",
        file_size=1,
        mime_type="text/markdown",
        md5_hash="a" * 32,
        page_kind="concept",
        wiki_slug="link-target",
        has_md=True,
    )
    orphan = FileModel(
        user_id=regular_user.id,
        filename="orphan.bin",
        original_name="orphan.txt",
        file_path="/tmp/orphan",
        file_size=1,
        mime_type="text/plain",
        md5_hash="b" * 32,
        page_kind="source",
    )
    db_session.add_all([src, target, orphan])
    db_session.flush()
    db_session.add(
        FileWikiLink(
            source_file_id=src.id,
            target_file_id=target.id,
            target_wiki_slug="link-target",
            link_kind="wiki",
            occurrence_index=0,
            anchor_id=f"test-out-{src.id}",
            start_offset=0,
            end_offset=10,
        )
    )
    db_session.commit()

    wiki_sec = render_wiki_section(db_session, regular_user.id)

    assert str(src.id) in wiki_sec
    assert str(orphan.id) not in wiki_sec
    assert str(target.id) not in wiki_sec


def test_file_stats_excludes_wiki_pages(db_session, regular_user):
    db_session.add(
        FileModel(
            user_id=regular_user.id,
            filename="w.bin",
            original_name="topic.md",
            file_path="/tmp/w",
            file_size=1,
            mime_type="text/markdown",
            md5_hash="e" * 32,
            page_kind="concept",
            wiki_slug="stats-skip",
        )
    )
    db_session.commit()

    stats = get_user_file_stats(db_session, regular_user.id)
    assert stats["total_files"] == 0
