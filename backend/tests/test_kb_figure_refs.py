# Copyright (c) 2026 徐泽宇
"""030 P2: figure_refs assembly + extract asset ACL."""

from __future__ import annotations

import os
from unittest.mock import patch

from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_chunk import KbChunk
from models.kb_enums import ContentKind
from services.extract.content_list_persist import extract_assets_dir_for_file
from services.kb_figure_refs import (
    _safe_asset_basename,
    build_figure_refs,
    resolve_figure_asset_rel_path,
)
from services.kb_search_service import search_kb
from tests.conftest import _create_user, make_jwt


def _vec(seed: float = 0.5) -> list[float]:
    return [seed] * OLLAMA_EMBED_DIM


def test_build_figure_refs_with_asset_path(db_session, regular_user, tmp_path):
    parent = tmp_path / "user" / "1"
    parent.mkdir(parents=True)
    f = FileModel(
        filename="doc.pdf",
        original_name="doc.pdf",
        file_path=str(parent / "doc.pdf"),
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    assets = extract_assets_dir_for_file(f)
    os.makedirs(assets, exist_ok=True)
    with open(os.path.join(assets, "fig1.jpg"), "wb") as fh:
        fh.write(b"fake-jpeg")
    meta = {
        "page_idx": 1,
        "asset_key": "fig1.jpg",
        "caption": "示意图",
    }
    refs = build_figure_refs(f, ContentKind.figure.value, meta)
    assert refs is not None
    assert refs["preview_url"] == f"/api/files/{f.id}/preview"
    assert refs["asset_key"] == "fig1.jpg"
    assert refs["asset_path"]
    assert f".extract_assets/{f.id}/fig1.jpg" in refs["asset_path"]
    assert refs["page"] == 2  # page_idx 1-based 展示（与 025 citation 对齐）
    assert refs["caption"] == "示意图"


def test_build_figure_refs_skips_text_kind(regular_user, tmp_path):
    f = FileModel(
        filename="a.pdf",
        original_name="a.pdf",
        file_path=str(tmp_path / "a.pdf"),
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    assert build_figure_refs(f, ContentKind.text.value, {}) is None


@patch("services.kb_search_service.embed_text")
def test_search_hit_includes_figure_refs(mock_embed, db_session, regular_user, tmp_path):
    mock_embed.return_value = _vec(1.0)
    parent = tmp_path / "u"
    parent.mkdir()
    f = FileModel(
        filename="a",
        original_name="报告.pdf",
        file_path=str(parent / "a.pdf"),
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    assets = extract_assets_dir_for_file(f)
    os.makedirs(assets, exist_ok=True)
    with open(os.path.join(assets, "fig1.jpg"), "wb") as fh:
        fh.write(b"img")
    db_session.add(
        KbChunk(
            user_id=regular_user.id,
            file_id=f.id,
            chunk_index=0,
            source="sidecar_md",
            text="示意图说明",
            content_kind=ContentKind.figure.value,
            content_meta={"page_idx": 0, "asset_key": "fig1.jpg"},
            char_start=0,
            char_end=6,
            embedding=_vec(0.9),
            embedding_model="test-model",
        )
    )
    db_session.commit()

    items, _, _, _ = search_kb(
        db_session,
        regular_user.id,
        "示意图",
        top_k=5,
        hybrid=False,
        modality_boost=False,
    )
    assert items
    assert items[0].get("figure_refs")
    assert items[0]["figure_refs"]["asset_key"] == "fig1.jpg"
    assert "asset_path" in items[0]["figure_refs"]


def test_safe_asset_basename_rejects_encoded_traversal():
    assert _safe_asset_basename("..%2Fetc%2Fpasswd") is None
    assert _safe_asset_basename("fig1.jpg") == "fig1.jpg"


def test_extract_asset_forbidden_for_other_user(client, db_session, regular_user, tmp_path):
    # ACL：_get_file_for_stream 对无权用户统一 404（不暴露文件是否存在）
    other = _create_user(db_session, "otherfiguser")
    other_token = make_jwt(other.id, other.password_rev)
    parent = tmp_path / "owner"
    parent.mkdir()
    f = FileModel(
        filename="secret.pdf",
        original_name="secret.pdf",
        file_path=str(parent / "secret.pdf"),
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    assets = extract_assets_dir_for_file(f)
    os.makedirs(assets, exist_ok=True)
    with open(os.path.join(assets, "fig1.jpg"), "wb") as fh:
        fh.write(b"img")

    resp = client.get(
        f"/api/files/{f.id}/extract-assets/fig1.jpg",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


def test_resolve_figure_asset_rel_path_under_upload_dir(regular_user, tmp_path):
    rel_parent = os.path.join("testuser", "2025-06")
    abs_parent = os.path.join(UPLOAD_DIR, rel_parent)
    os.makedirs(abs_parent, exist_ok=True)
    f = FileModel(
        filename="x.pdf",
        original_name="x.pdf",
        file_path=os.path.join(abs_parent, "x.pdf"),
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    assets = extract_assets_dir_for_file(f)
    os.makedirs(assets, exist_ok=True)
    with open(os.path.join(assets, "fig1.jpg"), "wb") as fh:
        fh.write(b"img")
    rel = resolve_figure_asset_rel_path(f, {"asset_key": "fig1.jpg"})
    assert rel
    assert not rel.startswith("/")
    assert ".extract_assets" in rel

def test_extract_asset_nested_images_subdir(regular_user, tmp_path):
    """MinerU stores figures under .extract_assets/{id}/images/*.jpg."""
    from services.kb_figure_refs import extract_asset_abs_path_for_key

    parent = tmp_path / "user" / "2" / "2026-06"
    parent.mkdir(parents=True)
    f = FileModel(
        filename="doc.pdf",
        original_name="doc.pdf",
        file_path=str(parent / "doc.pdf"),
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    f.id = 250
    assets = extract_assets_dir_for_file(f)
    images = os.path.join(assets, "images")
    os.makedirs(images, exist_ok=True)
    key = "81658cc15fc99a0b52c2b39e378b2a62e8a1f367adaf677c1b3c9a987eb7e590.jpg"
    with open(os.path.join(images, key), "wb") as fh:
        fh.write(b"img")
    abs_path = extract_asset_abs_path_for_key(f, key)
    assert abs_path and os.path.isfile(abs_path)

