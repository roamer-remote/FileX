# Copyright (c) 2026 徐泽宇
"""017: POST /search expand_wiki_links 内嵌 wiki_context。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from services.workspace_service import ensure_personal_workspace

CITATION_STUB = {"citation_label": "doc", "citation_tier": "document_only"}


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


def test_search_expand_wiki_links_embeds_context(client, db_session, regular_user, jwt_token, tmp_path, monkeypatch):
    personal = ensure_personal_workspace(db_session, regular_user)
    h = {"Authorization": f"Bearer {jwt_token}"}
    a = _add_source(db_session, regular_user.id, personal.id, tmp_path, "seed.txt", "a" * 32)
    b = _add_source(db_session, regular_user.id, personal.id, tmp_path, "peer.txt", "b" * 32)
    client.put(
        f"/api/files/{a.id}/md",
        headers=h,
        json={"content": "topic alpha [[file:" + str(b.id) + "]]\n"},
    )
    client.put(f"/api/files/{b.id}/md", headers=h, json={"content": "# peer body alpha\n"})

    def fake_search(*args, **kwargs):
        return (
            [
                {
                    "file_id": a.id,
                    "original_name": a.original_name,
                    "has_md": True,
                    "chunk_index": 0,
                    "source": "md",
                    "text": "topic alpha",
                    "score": 0.9,
                    "char_start": 0,
                    "char_end": 11,
                    **CITATION_STUB,
                }
            ],
            "test-model",
            1,
            {},
        )

    monkeypatch.setattr("routers.knowledge_base.search_kb", fake_search)

    r = client.post(
        "/api/knowledge-base/search",
        headers=h,
        json={"query": "alpha", "group_by_file": True, "expand_wiki_links": True},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("wiki_context") is not None
    node_ids = [n["file_id"] for n in data["wiki_context"]["nodes"]]
    assert a.id in node_ids and b.id in node_ids


def test_search_expand_wiki_links_no_hits(client, db_session, regular_user, jwt_token, monkeypatch):
    h = {"Authorization": f"Bearer {jwt_token}"}

    def fake_search(*args, **kwargs):
        return ([], "test-model", 0, {})

    monkeypatch.setattr("routers.knowledge_base.search_kb", fake_search)
    data = client.post(
        "/api/knowledge-base/search",
        headers=h,
        json={"query": "none", "expand_wiki_links": True},
    ).json()
    assert data.get("wiki_context") is None


def test_search_expand_wiki_links_respects_wiki_context_depth(
    client, db_session, regular_user, jwt_token, monkeypatch
):
    captured: dict = {}

    def fake_batch(db, actor, file_ids, **kwargs):
        captured.update(kwargs)
        return {
            "seed_file_ids": file_ids,
            "depth": kwargs.get("depth", 1),
            "max_files": kwargs.get("max_files", 8),
            "truncated": False,
            "skipped": [],
            "nodes": [],
            "fetched_at": "2026-06-09T00:00:00Z",
        }

    def fake_search(*args, **kwargs):
        return (
            [
                {
                    "file_id": 1,
                    "original_name": "a.txt",
                    "has_md": True,
                    "chunk_index": 0,
                    "source": "md",
                    "text": "topic",
                    "score": 0.9,
                    "char_start": 0,
                    "char_end": 5,
                    **CITATION_STUB,
                }
            ],
            "test-model",
            1,
            {},
        )

    def fake_hint(db, actor, seed_ids, *, depth=1, max_files=8):
        from schemas.kb import WikiContextHint

        return WikiContextHint(
            required=True,
            seed_file_ids=seed_ids,
            expandable_seed_ids=seed_ids,
            outlink_counts={seed_ids[0]: 1},
            recommended_parallel=1,
            depth=depth,
            max_files=max_files,
        )

    monkeypatch.setattr("routers.knowledge_base.search_kb", fake_search)
    monkeypatch.setattr("services.kb_search_wiki_hint.build_wiki_context_hint", fake_hint)
    monkeypatch.setattr("services.wiki_context_service.expand_wiki_context_batch", fake_batch)

    h = {"Authorization": f"Bearer {jwt_token}"}
    client.post(
        "/api/knowledge-base/search",
        headers=h,
        json={
            "query": "topic",
            "expand_wiki_links": True,
            "expand_wiki_coref": True,
            "wiki_context_depth": 2,
        },
    )
    assert captured.get("depth") == 2
    assert captured.get("include_coref") is True
