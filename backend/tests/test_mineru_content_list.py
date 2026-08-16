# Copyright (c) 2026 徐泽宇
"""030 P0: MinerU content_list, asset paths, degradation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest

from config import OLLAMA_EMBED_DIM, UPLOAD_DIR
from models.file import File as FileModel
from models.kb_enums import ContentKind
from services.extract.base import ExtractResult
from services.extract.content_list_markdown import content_list_to_markdown
from services.extract.content_list_persist import (
    CONTENT_LIST_SCHEMA,
    load_content_list_sidecar,
    normalize_content_list_asset_paths,
    parse_content_list_form_json,
    prepare_structured_extract,
    write_content_list_sidecar,
)
from services.extract.content_markers import format_content_marker
from services.extract.providers.mineru_provider import extract_mineru
from services.extract.providers.registry import extract_with_provider
from services.kb_chunking import chunk_markdown
from services.kb_content_kind import enrich_chunks_with_content_metadata
from services.kb_extract_service import persist_extract_result
from services.kb_index_service import run_index_job
from services.system_setting_service import KEY_KB_EXTRACT_PROVIDER, update_settings


def _vec(seed=0.42):
    return [seed] * OLLAMA_EMBED_DIM


def test_content_list_to_markdown_figure_marker():
    items = [
        {
            "type": "image",
            "img_path": "user/1/.extract_assets/9/fig1.jpg",
            "page_idx": 1,
            "image_caption": ["Fig 1"],
        }
    ]
    md = content_list_to_markdown(items)
    assert "filex:content" in md
    assert ContentKind.figure.value in md
    assert "![Fig 1]" in md
    assert "page=2" in md
    assert "filex:loc" in md


def test_normalize_content_list_asset_path_resolved(regular_user, tmp_path):
    rel_dir = os.path.join(str(regular_user.id), "2026-06")
    user_dir = os.path.join(UPLOAD_DIR, rel_dir)
    os.makedirs(user_dir, exist_ok=True)
    pdf_path = os.path.join(user_dir, "doc.pdf")
    Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
    Path(pdf_path).write_bytes(b"%PDF-1.4")

    f = FileModel(
        filename="doc.pdf",
        original_name="doc.pdf",
        file_path=pdf_path,
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )

    mineru_assets = tmp_path / "mineru_assets"
    mineru_assets.mkdir()
    (mineru_assets / "fig1.jpg").write_bytes(b"JPEGDATA")

    content_list = [{"type": "image", "img_path": "/data/out/fig1.jpg", "page_idx": 0}]
    normalized = normalize_content_list_asset_paths(f, content_list, str(mineru_assets))
    assert len(normalized) == 1
    rel = normalized[0]["img_path"]
    abs_path = os.path.join(UPLOAD_DIR, rel)
    assert os.path.isfile(abs_path)
    with open(abs_path, "rb") as fh:
        assert fh.read() == b"JPEGDATA"


def test_normalize_nested_mineru_images_layout(regular_user, tmp_path):
    """MinerU assets_dir is auto/ with images/*.jpg; img_path is images/hash.jpg."""
    rel_dir = os.path.join(str(regular_user.id), "2026-06")
    user_dir = os.path.join(UPLOAD_DIR, rel_dir)
    os.makedirs(user_dir, exist_ok=True)
    pdf_path = os.path.join(user_dir, "nested.pdf")
    Path(pdf_path).write_bytes(b"%PDF-1.4")

    f = FileModel(
        filename="nested.pdf",
        original_name="nested.pdf",
        file_path=pdf_path,
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    f.id = 245

    auto_dir = tmp_path / "auto"
    images = auto_dir / "images"
    images.mkdir(parents=True)
    (images / "abc.jpg").write_bytes(b"JPEGDATA")

    content_list = [
        {"type": "image", "img_path": "images/abc.jpg", "page_idx": 0, "image_caption": ["Fig A"]},
    ]
    normalized = normalize_content_list_asset_paths(f, content_list, str(auto_dir))
    assert len(normalized) == 1
    assert normalized[0]["img_path"].endswith("images/abc.jpg")
    md = content_list_to_markdown(normalized)
    assert "filex:content" in md
    assert ContentKind.figure.value in md

    asset_abs = os.path.join(UPLOAD_DIR, normalized[0]["img_path"])
    assert os.path.isfile(asset_abs)


def test_prepare_structured_extract_writes_sidecar(regular_user, tmp_path):
    rel_dir = os.path.join(str(regular_user.id), "2026-06")
    user_dir = os.path.join(UPLOAD_DIR, rel_dir)
    os.makedirs(user_dir, exist_ok=True)
    pdf_path = os.path.join(user_dir, "doc2.pdf")
    Path(pdf_path).write_bytes(b"%PDF-1.4")

    f = FileModel(
        filename="doc2.pdf",
        original_name="doc2.pdf",
        file_path=pdf_path,
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_id = 42
    f.id = db_id

    mineru_assets = tmp_path / "assets"
    mineru_assets.mkdir()
    (mineru_assets / "f.jpg").write_bytes(b"IMG")

    md = prepare_structured_extract(
        f,
        [{"type": "image", "img_path": "/tmp/f.jpg", "page_idx": 0}],
        str(mineru_assets),
    )
    assert "filex:content" in md
    sidecar_path = os.path.join(UPLOAD_DIR, ".md_notes", f"{db_id}.content_list.json")
    assert os.path.isfile(sidecar_path)
    with open(sidecar_path, encoding="utf-8") as fh:
        wrapper = json.load(fh)
    assert wrapper["schema"] == CONTENT_LIST_SCHEMA
    assert wrapper["version"] == 1


@patch("services.extract.providers.mineru_provider.MINERU_URL", "http://mineru.test")
@patch("httpx.Client")
def test_mineru_sidecar_markdown_only_legacy(mock_client_cls, regular_user, tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="a.pdf",
        original_name="a.pdf",
        file_path=str(pdf),
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    mock_resp = mock_client_cls.return_value.__enter__.return_value.post.return_value
    mock_resp.raise_for_status = lambda: None
    mock_resp.json.return_value = {"markdown": "# legacy md"}

    result = extract_mineru(f)
    assert result.text == "# legacy md"
    assert result.content_list is None
    assert result.engine == "mineru"


@patch("services.extract.providers.mineru_provider.MINERU_URL", "http://mineru.test")
@patch("httpx.Client")
def test_mineru_sidecar_no_content_list(mock_client_cls, regular_user, tmp_path):
    pdf = tmp_path / "b.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="b.pdf",
        original_name="b.pdf",
        file_path=str(pdf),
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    mock_resp = mock_client_cls.return_value.__enter__.return_value.post.return_value
    mock_resp.raise_for_status = lambda: None
    mock_resp.json.return_value = {"text": "plain only"}

    result = extract_mineru(f)
    assert result.content_list is None
    assert result.text == "plain only"
    assert result.engine == "mineru"


@patch("services.extract.providers.mineru_provider.MINERU_URL", "http://mineru.test")
@patch("httpx.Client")
def test_mineru_sidecar_empty_content_list(mock_client_cls, regular_user, tmp_path):
    pdf = tmp_path / "c.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="c.pdf",
        original_name="c.pdf",
        file_path=str(pdf),
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    mock_resp = mock_client_cls.return_value.__enter__.return_value.post.return_value
    mock_resp.raise_for_status = lambda: None
    mock_resp.json.return_value = {"markdown": "body", "content_list": []}

    result = extract_mineru(f)
    assert result.content_list == []
    assert result.engine == "mineru"


@patch("services.extract.providers.registry._legacy_extract")
def test_mineru_sidecar_503_fallback(mock_legacy, db_session, regular_user, tmp_path):
    update_settings(db_session, {KEY_KB_EXTRACT_PROVIDER: "mineru"})
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="d.pdf",
        original_name="d.pdf",
        file_path=str(pdf),
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    mock_legacy.return_value = ExtractResult(text="fallback ok", engine="legacy")

    with patch(
        "services.extract.providers.mineru_provider.extract_mineru",
        side_effect=httpx.HTTPStatusError("503", request=httpx.Request("POST", "http://x"), response=httpx.Response(503)),
    ):
        result = extract_with_provider(f, db_session)

    assert result.text == "fallback ok"
    assert result.engine == "legacy"
    assert result.fallback_from == "mineru"
    mock_legacy.assert_called_once()


def test_persist_extract_result_no_content_list_uses_text(db_session, regular_user, tmp_path):
    rel_dir = os.path.join(str(regular_user.id), "2026-06")
    user_dir = os.path.join(UPLOAD_DIR, rel_dir)
    os.makedirs(user_dir, exist_ok=True)
    pdf_path = os.path.join(user_dir, "e.pdf")
    Path(pdf_path).write_bytes(b"%PDF-1.4")

    f = FileModel(
        filename="e.pdf",
        original_name="e.pdf",
        file_path=pdf_path,
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()

    result = ExtractResult(text="flat body", engine="mineru", content_list=None)
    persist_extract_result(db_session, f, result, user_id=regular_user.id)
    db_session.commit()
    assert f.extract_status == "ready"
    assert f.extract_engine == "mineru"
    from services.md_paths import md_note_path
    from services.okf.frontmatter import split_frontmatter

    with open(md_note_path(f.id), encoding="utf-8") as fh:
        _metadata, body = split_frontmatter(fh.read())
        assert body.strip() == "flat body"


def test_enrich_chunks_figure_content_kind():
    marker = format_content_marker(ContentKind.figure.value, page=2, asset_key="fig.jpg")
    body = marker + "![alt](path/to/fig.jpg)"
    pieces = chunk_markdown(body)
    enriched = enrich_chunks_with_content_metadata(body, pieces)
    kinds = [row[1] for row in enriched]
    assert ContentKind.figure.value in kinds


@patch("services.kb_embed_cache_service.embed_texts")
@patch("services.kb_index_service.resolve_index_text")
def test_index_job_persists_content_kind(mock_resolve, mock_embed, db_session, regular_user, tmp_path):
    mock_embed.side_effect = lambda texts, **_kwargs: [_vec() for _ in texts]
    marker = format_content_marker(ContentKind.table.value, page=0)
    sidecar = marker + "|a|b|\n|1|2|"
    mock_resolve.return_value = (sidecar, "sidecar_md")

    f = FileModel(
        filename="t.pdf",
        original_name="t.pdf",
        file_path=str(tmp_path / "t.pdf"),
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=str(tmp_path / "note.md"),
        index_status="pending",
    )
    db_session.add(f)
    db_session.commit()

    from models.kb_index_job import KbIndexJob

    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="queued")
    db_session.add(job)
    db_session.commit()

    run_index_job(db_session, job)

    from models.kb_chunk import KbChunk

    chunk = db_session.query(KbChunk).filter(
        KbChunk.file_id == f.id, KbChunk.content_kind == ContentKind.table.value,
    ).first()
    assert chunk is not None
    assert chunk.content_meta is not None




def test_rel_upload_path_under_upload_dir(tmp_path, monkeypatch):
    from config import UPLOAD_DIR as CFG_UPLOAD
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    monkeypatch.setattr("config.UPLOAD_DIR", str(upload_root))
    monkeypatch.setattr("services.extract.content_list_persist.UPLOAD_DIR", str(upload_root))

    inner = upload_root / "1" / "2026-06"
    inner.mkdir(parents=True)
    file_abs = inner / "doc.pdf"
    file_abs.write_bytes(b"x")

    from services.extract.content_list_persist import _rel_upload_path

    rel = _rel_upload_path(str(file_abs))
    assert rel == "1/2026-06/doc.pdf"


@patch("services.kb_index_service._notify_file_index")
@patch("services.kb_embed_cache_service.embed_texts")
@patch("services.kb_index_service.resolve_index_text")
def test_index_job_prefix_offset_alignment(mock_resolve, mock_embed, _mock_notify, db_session, regular_user, tmp_path):
    mock_embed.side_effect = lambda texts, **_kwargs: [_vec() for _ in texts]
    marker = format_content_marker(ContentKind.table.value, page=1)
    sidecar = marker + "|a|b|\n|1|2|"
    mock_resolve.return_value = (sidecar, "sidecar_md")

    f = FileModel(
        filename="发票.pdf",
        original_name="发票.pdf",
        file_path=str(tmp_path / "发票.pdf"),
        file_size=10,
        mime_type="application/pdf",
        user_id=regular_user.id,
        has_md=True,
        md_file_path=str(tmp_path / "note.md"),
        index_status="pending",
    )
    db_session.add(f)
    db_session.commit()

    from models.kb_index_job import KbIndexJob
    from models.kb_chunk import KbChunk

    job = KbIndexJob(user_id=regular_user.id, file_id=f.id, status="queued")
    db_session.add(job)
    db_session.commit()

    prefix_len = len(f"【{f.original_name}】\n\n")
    run_index_job(db_session, job)

    chunks = (
        db_session.query(KbChunk)
        .filter(KbChunk.file_id == f.id)
        .order_by(KbChunk.chunk_index)
        .all()
    )
    assert chunks
    assert all(c.char_start >= 0 and c.char_end >= c.char_start for c in chunks)

    table_chunk = next((c for c in chunks if c.content_kind == ContentKind.table.value), None)
    assert table_chunk is not None
    assert table_chunk.char_start >= prefix_len
    assert table_chunk.content_meta is not None

def test_parse_content_list_form_json_wrapper():
    raw = json.dumps({"version": 1, "schema": CONTENT_LIST_SCHEMA, "content_list": [{"type": "text", "text": "hi"}]})
    items = parse_content_list_form_json(raw)
    assert items[0]["text"] == "hi"


def test_external_content_list_form(client, db_session):
    from tests.conftest import _create_api_key, _create_user

    user = _create_user(db_session, f"cl_user_{uuid4().hex}")
    key = _create_api_key(db_session, user)
    content = b"external-bytes-unique-030"
    cl = json.dumps({"version": 1, "schema": CONTENT_LIST_SCHEMA, "content_list": [{"type": "text", "text": "ext"}]})
    resp = client.post(
        "/api/external/files-with-md",
        headers={"Authorization": f"Bearer {key._plaintext}"},
        files={"file": ("doc.txt", content, "text/plain")},
        data={"content_list": cl},
    )
    assert resp.status_code == 200, resp.text
    file_id = resp.json()["file"]["id"]
    sidecar = load_content_list_sidecar(file_id)
    assert sidecar is not None and sidecar[0]["text"] == "ext"
