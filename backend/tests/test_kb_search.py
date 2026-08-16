# Copyright (c) 2026 徐泽宇
"""Semantic search tenant isolation (mocked query embed).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
import pytest
from schemas.kb import KbChunkHit
from services.kb_search_service import _merge_hits_by_file, search_kb
from services.system_setting_service import KEY_KB_SEARCH_HYBRID_ENABLED, invalidate_settings_cache, update_settings
from services.workspace_service import ensure_personal_workspace


@pytest.fixture(autouse=True)
def _disable_hybrid_search_for_vector_tests(db_session):
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    invalidate_settings_cache()
    yield



def _vec(seed: float) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


def _ready_file(user, ws, name: str) -> FileModel:
    return FileModel(
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="text/markdown",
        user_id=user.id,
        workspace_id=ws.id,
        index_status="ready",
    )


def _chunk(user, file: FileModel, text: str, seed: float) -> KbChunk:
    return KbChunk(
        user_id=user.id,
        workspace_id=file.workspace_id,
        file_id=file.id,
        chunk_index=0,
        source="main_md",
        text=text,
        char_start=0,
        char_end=len(text),
        embedding=_vec(seed),
        embedding_model="test-model",
    )


@patch("services.kb_search_service.embed_text")
def test_search_scoped_to_user(mock_embed, db_session, regular_user, admin_user):
    mock_embed.return_value = _vec(0.5)
    f1 = FileModel(
        filename="a",
        original_name="u1.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    f2 = FileModel(
        filename="b",
        original_name="u2.pdf",
        file_path="/tmp/b",
        file_size=1,
        mime_type="application/pdf",
        user_id=admin_user.id,
        index_status="ready",
    )
    db_session.add_all([f1, f2])
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f1.id,
            chunk_index=0,
            source="sidecar_md",
            text="microscopy secret",
            char_start=0,
            char_end=10,
            embedding=_vec(0.1),
            embedding_model="test-model",
        )
    )
    db_session.add(
        KbChunk(
            user_id=admin_user.id,
            file_id=f2.id,
            chunk_index=0,
            source="sidecar_md",
            text="admin only",
            char_start=0,
            char_end=10,
            embedding=_vec(0.9),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    items, model, k, _meta = search_kb(db_session, regular_user.id, "microscopy", top_k=5)
    assert k == 5
    assert len(items) == 1
    assert items[0]["file_id"] == f1.id
    assert "microscopy" in items[0]["text"]


@patch("services.kb_search_service.embed_text")
def test_search_api_union_tags_intersects_readable_subquery(
    mock_embed,
    monkeypatch,
    client,
    db_session,
    regular_user,
    jwt_token,
):
    from services.tag_service import replace_file_tags

    mock_embed.return_value = _vec(0.5)
    ws = ensure_personal_workspace(db_session, regular_user)
    visible = _ready_file(regular_user, ws, "visible.md")
    hidden = _ready_file(regular_user, ws, "hidden.md")
    db_session.add_all([visible, hidden])
    db_session.commit()
    replace_file_tags(db_session, regular_user.id, hidden.id, ["union-tag"])
    db_session.add_all(
        [
            _chunk(regular_user, visible, "alpha visible", 0.9),
            _chunk(regular_user, hidden, "alpha hidden tagged", 0.8),
        ]
    )
    db_session.commit()

    def only_visible_subquery(db, user, workspace_id, *, member=None):
        return select(FileModel.id).where(FileModel.id == visible.id)

    monkeypatch.setattr(
        "routers.knowledge_base.readable_file_ids_subquery",
        only_visible_subquery,
    )

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": "alpha",
            "top_k": 8,
            "tags": ["union-tag"],
            "tag_combine": "union",
            "group_by_file": True,
        },
    )

    assert resp.status_code == 200, resp.text
    ids = {int(item["file_id"]) for item in resp.json()["items"]}
    assert visible.id in ids
    assert hidden.id not in ids


@patch("services.kb_search_service.embed_text")
def test_search_api_cross_workspace_uses_readable_subquery(
    mock_embed,
    monkeypatch,
    client,
    db_session,
    regular_user,
    jwt_token,
):
    from services.workspace_service import create_shared_workspace

    mock_embed.return_value = _vec(0.5)
    personal = ensure_personal_workspace(db_session, regular_user)
    shared = create_shared_workspace(db_session, name="cross-search-sql", owner=regular_user)
    pf = _ready_file(regular_user, personal, "personal-cross.md")
    sf = _ready_file(regular_user, shared, "shared-cross.md")
    db_session.add_all([pf, sf])
    db_session.commit()
    db_session.add_all(
        [
            _chunk(regular_user, pf, "alpha personal", 0.9),
            _chunk(regular_user, sf, "alpha shared", 0.8),
        ]
    )
    db_session.commit()

    def fail_materialized_union(db, user):
        raise AssertionError("cross-workspace non-cache search should use readable subquery")

    monkeypatch.setattr(
        "routers.knowledge_base.accessible_file_ids_all_member_workspaces",
        fail_materialized_union,
    )

    resp = client.post(
        "/api/knowledge-base/search?cross_workspace=true",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"query": "alpha", "top_k": 8, "group_by_file": True},
    )

    assert resp.status_code == 200, resp.text
    ids = {int(item["file_id"]) for item in resp.json()["items"]}
    assert {pf.id, sf.id}.issubset(ids)


@patch("services.kb_search_service.embed_text")
def test_search_merges_chunks_from_same_file(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(0.5)
    f = FileModel(
        filename="a",
        original_name="merged.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    for i, score_seed in enumerate((0.2, 0.05, 0.15)):
        db_session.add(
            KbChunk(
                user_id=regular_user.id,
                file_id=f.id,
                chunk_index=i,
                source="sidecar_md",
                text=f"chunk {i} microscopy",
                char_start=i * 10,
                char_end=i * 10 + 9,
                embedding=_vec(score_seed),
                embedding_model="test-model",
            )
        )
    db_session.commit()

    items, _, k, _meta = search_kb(
        db_session, regular_user.id, "microscopy", top_k=8, group_by_file=True
    )
    assert k == 8
    assert len(items) == 1
    assert items[0]["file_id"] == f.id
    assert items[0]["matched_chunks"] == 3
    assert items[0]["chunk_index"] in (0, 1, 2)
    assert len(items[0]["snippets"]) == 3


@patch("services.kb_search_service.embed_text")
def test_search_returns_multiple_chunks_by_default(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(0.5)
    f = FileModel(
        filename="a",
        original_name="multi.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    for i, seed in enumerate((0.2, 0.05, 0.15)):
        db_session.add(
            KbChunk(
                user_id=regular_user.id,
                file_id=f.id,
                chunk_index=i,
                source="sidecar_md",
                text=f"chunk {i} microscopy",
                char_start=i * 10,
                char_end=i * 10 + 9,
                embedding=_vec(seed),
                embedding_model="test-model",
            )
        )
    db_session.commit()
    items, _, _, _meta = search_kb(db_session, regular_user.id, "microscopy", top_k=8)
    assert len(items) == 3


@patch("services.kb_search_service.embed_text")
def test_search_excludes_non_ready_by_default(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(0.5)
    f = FileModel(
        filename="a",
        original_name="pending.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="pending",
    )
    db_session.add(f)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text="microscopy pending",
            char_start=0,
            char_end=10,
            embedding=_vec(0.1),
            embedding_model="test-model",
        )
    )
    db_session.commit()
    items, _, _, _meta = search_kb(db_session, regular_user.id, "microscopy", top_k=5)
    assert len(items) == 0


@patch("services.kb_search_service.embed_text")
def test_search_short_query_filters_files_without_keyword(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(0.9)
    with_term = FileModel(
        filename="a.md",
        original_name="有嘟嘟.md",
        file_path="/tmp/a",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    without_term = FileModel(
        filename="b.md",
        original_name="无关笔记.md",
        file_path="/tmp/b",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add_all([with_term, without_term])
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=with_term.id,
            chunk_index=0,
            source="main_md",
            text="这里提到嘟嘟",
            char_start=0,
            char_end=6,
            embedding=_vec(0.2),
            embedding_model="test-model",
        )
    )
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=without_term.id,
            chunk_index=0,
            source="main_md",
            text="完全不同的科研笔记内容",
            char_start=0,
            char_end=10,
            embedding=_vec(0.05),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    items, _, _, _meta = search_kb(db_session, regular_user.id, "嘟嘟", top_k=8)
    assert len(items) == 1
    assert items[0]["file_id"] == with_term.id

@patch("services.kb_search_service.embed_text")
def test_search_tag_combine_union_includes_tagged_and_vector_hits(mock_embed, db_session, regular_user):
    """tag_combine=union: tagged files plus vector hits outside tag filter."""
    from services.tag_service import replace_file_tags

    mock_embed.return_value = _vec(0.5)
    tagged = FileModel(
        filename="tagged.md",
        original_name="tagged-only.md",
        file_path="/tmp/tagged",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    semantic = FileModel(
        filename="semantic.md",
        original_name="semantic-hit.md",
        file_path="/tmp/semantic",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add_all([tagged, semantic])
    db_session.commit()
    replace_file_tags(db_session, regular_user.id, tagged.id, ["重要资料"])
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=tagged.id,
            chunk_index=0,
            source="main_md",
            text="归档摘要，正文与查询词无关",
            char_start=0,
            char_end=8,
            embedding=_vec(0.02),
            embedding_model="test-model",
        )
    )
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=semantic.id,
            chunk_index=0,
            source="main_md",
            text="重要资料相关的临床前研究结论",
            char_start=0,
            char_end=8,
            embedding=_vec(0.95),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    filtered, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        "重要资料 临床",
        top_k=8,
        tags=["重要资料"],
        tag_combine="filter",
        group_by_file=True,
    )
    assert {x["file_id"] for x in filtered} == {tagged.id}

    union_items, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        "重要资料 临床",
        top_k=8,
        tags=["重要资料"],
        tag_combine="union",
        group_by_file=True,
    )
    union_ids = {x["file_id"] for x in union_items}
    assert tagged.id in union_ids
    assert semantic.id in union_ids


@patch("services.kb_search_service.embed_text")
def test_search_source_files_only_excludes_wiki_theme_pages(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(0.5)
    source = FileModel(
        filename="src.bin",
        original_name="source.txt",
        file_path="/tmp/src",
        file_size=1,
        mime_type="text/plain",
        user_id=regular_user.id,
        index_status="ready",
        page_kind="source",
    )
    topic = FileModel(
        filename="topic.bin",
        original_name="topic.md",
        file_path="/tmp/topic",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
        page_kind="concept",
        wiki_slug="search-filter-test",
        has_md=True,
    )
    db_session.add_all([source, topic])
    db_session.commit()
    db_session.add_all(
        [
            KbChunk(
                user_id=regular_user.id,
                file_id=source.id,
                chunk_index=0,
                source="sidecar_md",
                text="source microscopy note",
                char_start=0,
                char_end=10,
                embedding=_vec(0.2),
                embedding_model="test-model",
            ),
            KbChunk(
                user_id=regular_user.id,
                file_id=topic.id,
                chunk_index=0,
                source="sidecar_md",
                text="topic microscopy wiki page",
                char_start=0,
                char_end=10,
                embedding=_vec(0.9),
                embedding_model="test-model",
            ),
        ]
    )
    db_session.commit()

    all_items, _, _, _ = search_kb(db_session, regular_user.id, "microscopy", top_k=5)
    assert {x["file_id"] for x in all_items} == {source.id, topic.id}

    source_only, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        "microscopy",
        top_k=5,
        source_files_only=True,
    )
    assert {x["file_id"] for x in source_only} == {source.id}


# --- 154: multi-repr search routing tests ---

def test_merge_hits_by_file_accepts_virtual_multi_repr_hit():
    """Virtual representation hits may not have chunk locator fields."""
    items = _merge_hits_by_file(
        [
            {
                "chunk_id": "repr:7541",
                "file_id": 42,
                "text": "RAPTOR 摘要命中",
                "score": 0.9,
                "source_kind": "multi_repr:raptor_summary",
            }
        ]
    )

    assert len(items) == 1
    assert items[0]["matched_chunks"] == 1
    assert items[0]["snippets"][0]["chunk_index"] is None


@patch("services.kb_search_service.embed_text")
def test_search_kb_routes_multi_repr_when_enabled(mock_embed, db_session, regular_user):
    """154 SC-154-014: multi_repr_enabled=True → search_repr 被调，meta.multi_repr_added_hits >= 1."""
    mock_embed.return_value = _vec(0.5)
    f = FileModel(
        filename="r.bin",
        original_name="r.md",
        file_path="/tmp/r",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text="raptor 摘要核心句",
            char_start=0,
            char_end=8,
            embedding=_vec(0.4),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    # 第二个文件：保证 repr_items 的 file_id 与 base chunk 不冲突（触发 merge 路径）
    f2 = FileModel(
        filename="r2.bin",
        original_name="r2.md",
        file_path="/tmp/r2",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f2)
    db_session.commit()
    with patch("services.kb_multi_repr_service.search_repr") as mock_repr:
        mock_repr.return_value = [
            {
                "id": 1,
                "file_id": f2.id,
                "representation_type": "raptor_summary",
                "text": "RAPTOR 摘要命中",
                "score": 0.9,
            }
        ]
        items, _, _, meta = search_kb(
            db_session,
            regular_user.id,
            "raptor 摘要",
            top_k=5,
            group_by_file=True,
            include_raptor_summaries=True,
            multi_repr_enabled=True,
            multi_repr_types=["raptor_summary", "event_summary"],
        )
        assert mock_repr.called
    assert meta.get("multi_repr_enabled") is True
    assert meta.get("multi_repr_added_hits", 0) >= 1
    raptor_hits = [it for it in items if it.get("source_kind", "").startswith("multi_repr:raptor_summary")]
    assert raptor_hits, f"expected multi_repr:raptor_summary hits, got items={items!r} meta={meta!r}"
    KbChunkHit(**raptor_hits[0])


@patch("services.kb_search_service.embed_text")
def test_search_kb_section_repr_returns_source_chunk_locator(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(0.5)
    f = FileModel(filename="section.md", original_name="section.md", file_path="/tmp/s", file_size=1, mime_type="text/markdown", user_id=regular_user.id, index_status="ready")
    db_session.add(f)
    db_session.commit()
    chunk = KbChunk(user_id=regular_user.id, file_id=f.id, chunk_index=4, source="sidecar_md", text="后段条款原文", heading_path="合同 / 违约责任", char_start=120, char_end=128, embedding=_vec(0.4), embedding_model="test-model")
    db_session.add(chunk)
    db_session.commit()
    with patch("services.kb_multi_repr_service.search_repr") as mock_repr:
        mock_repr.return_value = [{"id": 2, "file_id": f.id, "representation_type": "section_context", "source_id": f"chunk:{chunk.id}", "text": "章节摘要", "score": 0.9}]
        items, _, _, _ = search_kb(db_session, regular_user.id, "违约责任", top_k=5, multi_repr_enabled=True, multi_repr_types=["section_context"])
    hit = next(item for item in items if item.get("source_kind") == "multi_repr:section_context")
    assert hit["chunk_id"] == chunk.id
    assert hit["heading_path"] == "合同 / 违约责任"
    assert (hit["char_start"], hit["char_end"]) == (120, 128)


@patch("services.kb_search_service.embed_text")
def test_search_kb_section_repr_augments_existing_file_with_snippet(mock_embed, db_session, regular_user):
    mock_embed.return_value = _vec(0.5)
    f = FileModel(filename="long.md", original_name="long.md", file_path="/tmp/long", file_size=1, mime_type="text/markdown", user_id=regular_user.id, index_status="ready")
    db_session.add(f)
    db_session.commit()
    base = KbChunk(user_id=regular_user.id, file_id=f.id, chunk_index=0, source="sidecar_md", text="关键条款前段命中", heading_path="概述", char_start=0, char_end=8, embedding=_vec(0.4), embedding_model="test-model")
    section = KbChunk(user_id=regular_user.id, file_id=f.id, chunk_index=9, source="sidecar_md", text="后段关键条款", heading_path="合同 / 违约责任", char_start=200, char_end=206, embedding_model="test-model")
    db_session.add_all([base, section])
    db_session.commit()
    with patch("services.kb_multi_repr_service.search_repr") as mock_repr:
        mock_repr.return_value = [{"id": 3, "file_id": f.id, "representation_type": "section_context", "source_id": f"chunk:{section.id}", "text": "章节摘要", "score": 0.9}]
        items, _, _, _ = search_kb(db_session, regular_user.id, "关键条款", top_k=5, group_by_file=True, multi_repr_enabled=True, multi_repr_types=["section_context"])
    assert len([item for item in items if item["file_id"] == f.id]) == 1
    section_snippet = next(snip for snip in items[0]["snippets"] if snip["chunk_index"] == 9)
    assert section_snippet["chunk_id"] == section.id
    assert (section_snippet["char_start"], section_snippet["char_end"]) == (200, 206)
    assert section_snippet["heading_path"] == "合同 / 违约责任"


@patch("services.kb_search_service.embed_text")
def test_search_kb_section_repr_retains_distinct_section_without_file_grouping(
    mock_embed, db_session, regular_user,
):
    """A long-document section representation must not be discarded by file-level dedup."""
    mock_embed.return_value = _vec(0.5)
    f = FileModel(filename="long.md", original_name="long.md", file_path="/tmp/long", file_size=1, mime_type="text/markdown", user_id=regular_user.id, index_status="ready")
    db_session.add(f)
    db_session.commit()
    base = KbChunk(user_id=regular_user.id, file_id=f.id, chunk_index=0, source="sidecar_md", text="关键条款概述", heading_path="概述", char_start=0, char_end=6, embedding=_vec(0.4), embedding_model="test-model")
    section = KbChunk(user_id=regular_user.id, file_id=f.id, chunk_index=9, source="sidecar_md", text="后段关键条款", heading_path="合同 / 违约责任", char_start=200, char_end=206, embedding_model="test-model")
    db_session.add_all([base, section])
    db_session.commit()

    with patch("services.kb_multi_repr_service.search_repr") as mock_repr:
        mock_repr.return_value = [{"id": 4, "file_id": f.id, "representation_type": "section_context", "source_id": f"chunk:{section.id}", "text": "章节摘要", "score": 0.9}]
        items, _, _, _ = search_kb(
            db_session,
            regular_user.id,
            "关键条款",
            top_k=5,
            group_by_file=False,
            multi_repr_enabled=True,
            multi_repr_types=["section_context"],
        )

    assert any(item.get("chunk_id") == base.id for item in items)
    section_hit = next(item for item in items if item.get("source_kind") == "multi_repr:section_context")
    assert section_hit["chunk_id"] == section.id
    assert section_hit["heading_path"] == "合同 / 违约责任"
    assert (section_hit["char_start"], section_hit["char_end"]) == (200, 206)


@patch("services.kb_search_service.embed_text")
def test_grouped_search_reranks_chunk_candidates_before_file_merge(mock_embed, monkeypatch, db_session, regular_user):
    mock_embed.return_value = _vec(0.5)
    f = FileModel(filename="dense.md", original_name="dense.md", file_path="/tmp/dense", file_size=1, mime_type="text/markdown", user_id=regular_user.id, index_status="ready")
    db_session.add(f)
    db_session.commit()
    db_session.add_all([
        KbChunk(user_id=regular_user.id, file_id=f.id, chunk_index=index, source="sidecar_md", text=f"关键条款 {index}", char_start=index * 10, char_end=index * 10 + 4, embedding=_vec(0.4), embedding_model="test-model")
        for index in (0, 1)
    ])
    db_session.commit()
    captured = []
    monkeypatch.setattr("services.kb_search_service.rerank_hits", lambda _q, items, top_k: (captured.extend(items) or items, False))

    search_kb(db_session, regular_user.id, "关键条款", top_k=5, group_by_file=True)

    assert {item["chunk_index"] for item in captured} == {0, 1}


def test_router_multi_repr_types_include_section_context():
    from routers.knowledge_base import _coverage_multi_repr_types

    assert "section_context" in _coverage_multi_repr_types()


@patch("services.kb_search_service.embed_text")
def test_search_kb_no_multi_repr_when_disabled(mock_embed, db_session, regular_user):
    """154 SC-154-015: 默认 multi_repr_enabled=False → search_repr 不被调（保护 153/152/老用户）."""
    mock_embed.return_value = _vec(0.5)
    f = FileModel(
        filename="n.bin",
        original_name="n.md",
        file_path="/tmp/n",
        file_size=1,
        mime_type="text/markdown",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text="base chunk 命中句",
            char_start=0,
            char_end=6,
            embedding=_vec(0.6),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    with patch("services.kb_multi_repr_service.search_repr") as mock_repr:
        items, _, _, meta = search_kb(
            db_session,
            regular_user.id,
            "base chunk",
            top_k=5,
        )
        assert not mock_repr.called
    # 默认 multi_repr_enabled 路径下，search_kb 不会写 meta["multi_repr_enabled"]（保持 None / falsy）
    assert not meta.get("multi_repr_enabled"), f"expected falsy, got {meta.get('multi_repr_enabled')!r}"
    assert not any(it.get("source_kind", "").startswith("multi_repr:") for it in items)
