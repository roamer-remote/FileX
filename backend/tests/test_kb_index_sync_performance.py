from __future__ import annotations

from models.file import File as FileModel
from models.file_wiki_link import FileWikiLink
from services.knowledge_base_index_service import (
    auto_sync_kb_index,
    index_md_path,
    rebuild_and_save,
)


def _file(db, user, ws, name: str) -> FileModel:
    f = FileModel(
        user_id=user.id,
        workspace_id=ws.id,
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="text/plain",
        md5_hash="d" * 32,
        has_md=True,
        page_kind="source",
    )
    db.add(f)
    db.flush()
    return f


def test_sync_scope_auto_preserves_existing_wiki_section(db_session, regular_user):
    from services.workspace_service import ensure_personal_workspace

    ws = ensure_personal_workspace(db_session, regular_user)
    f = _file(db_session, regular_user, ws, "indexed.txt")
    db_session.add(
        FileWikiLink(
            source_file_id=f.id,
            target_file_id=None,
            target_wiki_slug="topic",
            target_file_id_raw=None,
            link_kind="wiki",
            link_text="topic",
            occurrence_index=0,
            anchor_id="scope-auto",
            start_offset=0,
            end_offset=5,
            broken_reason=None,
            content_hash=None,
        )
    )
    db_session.commit()
    rebuild_and_save(db_session, regular_user.id, sync_scope="all")
    before = index_md_path(regular_user.id).read_text(encoding="utf-8")

    f.original_name = "renamed.txt"
    db_session.flush()
    auto_sync_kb_index(db_session, regular_user.id, sync_scope="auto")
    after = index_md_path(regular_user.id).read_text(encoding="utf-8")

    assert "renamed.txt" in after
    assert "indexed.txt | 1 | 0" in after
    assert "<!-- KB_WIKI_INDEX_START -->" in before


def test_auto_sync_reentry_guard_prevents_nested_write(db_session, regular_user, monkeypatch):
    calls = {"n": 0}

    def fake_rebuild(db, user_id, *, sync_scope="all"):
        calls["n"] += 1
        auto_sync_kb_index(db, user_id, sync_scope=sync_scope)

    monkeypatch.setattr("services.knowledge_base_index_service.rebuild_and_save", fake_rebuild)

    auto_sync_kb_index(db_session, regular_user.id, sync_scope="auto")

    assert calls["n"] == 1


def test_wiki_page_routes_sync_only_wiki_scope(client, regular_user, jwt_token, monkeypatch):
    calls = []

    def fake_auto_sync(db, user_id, *, sync_scope="all"):
        calls.append((user_id, sync_scope))

    monkeypatch.setattr("services.knowledge_base_index_service.auto_sync_kb_index", fake_auto_sync)

    create_resp = client.post(
        "/api/knowledge-base/wiki/pages",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "title": "性能主题",
            "wiki_slug": "perf-topic",
            "page_kind": "concept",
            "markdown": "# 性能主题",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    file_id = int(create_resp.json()["file"]["id"])

    patch_resp = client.patch(
        f"/api/knowledge-base/wiki/pages/{file_id}",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"wiki_slug": "perf-topic-renamed"},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert calls == [(regular_user.id, "wiki"), (regular_user.id, "wiki")]


def test_admin_rebuild_wiki_links_syncs_wiki_scope(
    client,
    regular_user,
    admin_jwt_token,
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        "services.md_wiki_link_service.batch_rebuild_all_wiki_links",
        lambda db, actor, *, user_id=None, batch_size=100: {"rebuilt_count": 0, "file_count": 0},
    )

    def fake_auto_sync(db, user_id, *, sync_scope="all"):
        calls.append((user_id, sync_scope))

    monkeypatch.setattr("services.knowledge_base_index_service.auto_sync_kb_index", fake_auto_sync)

    resp = client.post(
        "/api/admin/kb/rebuild-wiki-links",
        headers={"Authorization": f"Bearer {admin_jwt_token}"},
        json={"user_id": regular_user.id, "batch_size": 100},
    )

    assert resp.status_code == 200, resp.text
    assert calls == [(regular_user.id, "wiki")]
