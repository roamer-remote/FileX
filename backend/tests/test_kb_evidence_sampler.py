# Copyright (c) 2026 徐泽宇
"""028 module B: Monte Carlo evidence sampler."""

from pathlib import Path
from unittest.mock import patch

from config import OLLAMA_EMBED_DIM
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from services.kb_evidence_sampler import (
    append_monte_carlo_hits,
    is_long_document,
    sample_evidence,
)
from services.kb_search_service import search_kb
from services.md_paths import md_note_path
from services.system_setting_service import KEY_KB_SEARCH_HYBRID_ENABLED, invalidate_settings_cache, update_settings


def _vec(a: float = 1.0) -> list[float]:
    v = [0.0] * OLLAMA_EMBED_DIM
    v[0] = a
    return v


def test_is_long_document_by_chars(db_session):
    assert is_long_document(db_session, 1, "x" * 8000, long_doc_chars=8000) is True
    assert is_long_document(db_session, 1, "short", long_doc_chars=8000) is False


def test_sample_evidence_returns_windows():
    md = ("报销流程 " * 500) + "关键条款说明"
    windows = sample_evidence(md, "报销", seed_char_offset=100, sample_k=3)
    assert len(windows) == 3
    for start, end, text, score in windows:
        assert 0 <= start < end <= len(md)
        assert text
        assert 0.0 <= score <= 1.0


@patch("services.kb_search_service.embed_text")
def test_append_monte_carlo_on_long_md(mock_embed, db_session, regular_user, tmp_path, monkeypatch):
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    invalidate_settings_cache()
    mock_embed.return_value = _vec(1.0)

    md_content = "报销制度详细说明。\n" + ("正文段落内容。" * 1200)
    f = FileModel(
        filename="a",
        original_name="长文档.pdf",
        file_path="/tmp/a",
        file_size=len(md_content),
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
        has_md=True,
    )
    db_session.add(f)
    db_session.commit()

    note_path = Path(md_note_path(f.id))
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(md_content, encoding="utf-8")
    f.md_file_path = str(note_path)
    db_session.add(f)
    db_session.commit()

    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text=md_content[:200],
            char_start=0,
            char_end=200,
            embedding=_vec(0.95),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    items, _, _, _ = search_kb(db_session, regular_user.id, "报销", top_k=3)
    merged, count = append_monte_carlo_hits(
        db_session,
        items,
        "报销",
        allowed_file_ids={f.id},
        long_doc_chars=8000,
        sample_k=2,
        max_files=3,
    )
    assert count >= 1
    mc = [x for x in merged if x.get("source_kind") == "monte_carlo_sample"]
    assert len(mc) >= 1


@patch("services.kb_search_service.embed_text")
def test_short_doc_skips_monte_carlo(mock_embed, db_session, regular_user):
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    invalidate_settings_cache()
    mock_embed.return_value = _vec(1.0)

    f = FileModel(
        filename="a",
        original_name="短文档.pdf",
        file_path="/tmp/a",
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
        has_md=False,
    )
    db_session.add(f)
    db_session.commit()
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text="短内容",
            char_start=0,
            char_end=3,
            embedding=_vec(0.9),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    items, _, _, _ = search_kb(db_session, regular_user.id, "短", top_k=3)
    merged, count = append_monte_carlo_hits(
        db_session,
        items,
        "短",
        allowed_file_ids={f.id},
        long_doc_chars=8000,
        sample_k=5,
        max_files=3,
    )
    assert count == 0
    assert len(merged) == len(items)


@patch("services.kb_search_service.embed_text")
def test_api_monte_carlo_sample_survives_top_k(
    mock_embed, client, db_session, regular_user, jwt_token, tmp_path, monkeypatch
):
    """P1 三次修复：finalize 后追加 Monte Carlo，top_k=1 时采样 hit 不被裁掉（028 SC-005）。"""
    update_settings(db_session, {KEY_KB_SEARCH_HYBRID_ENABLED: "false"})
    invalidate_settings_cache()
    mock_embed.return_value = _vec(1.0)

    md_content = "报销制度详细说明。\n" + ("正文段落内容。" * 1200)
    f = FileModel(
        filename="mc_api.pdf",
        original_name="mc_api.pdf",
        file_path=str(tmp_path / "mc_api.pdf"),
        file_size=len(md_content),
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
        has_md=True,
        publish_status="published",
    )
    db_session.add(f)
    db_session.commit()

    note_path = Path(md_note_path(f.id))
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(md_content, encoding="utf-8")
    f.md_file_path = str(note_path)
    db_session.add(f)
    db_session.commit()

    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text=md_content[:200],
            char_start=0,
            char_end=200,
            embedding=_vec(0.95),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    resp = client.post(
        "/api/knowledge-base/search",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={
            "query": "报销",
            "top_k": 1,
            "evidence_mode": "monte_carlo",
            "debug": True,
            "group_by_file": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    mc_hits = [x for x in body["items"] if x.get("source_kind") == "monte_carlo_sample"]
    assert len(mc_hits) >= 1
    assert body["meta"]["monte_carlo_sample_count"] >= 1
