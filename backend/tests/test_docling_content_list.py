# Copyright (c) 2026 徐泽宇
"""050: Docling content_list adapter + provider (SC-050-002/003/004)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import httpx

from models.file import File as FileModel
from models.kb_enums import ContentKind
from services.extract.content_list_markdown import content_list_to_markdown
from services.extract.content_list_persist import normalize_content_list_asset_paths, prepare_structured_extract
from services.extract.docling_content_list_adapter import adapt_docling_block, adapt_docling_content_list
from services.extract.providers.docling_provider import _parse_docling_payload, extract_docling
from services.extract.providers.registry import extract_with_provider
from services.extract.base import ExtractResult
from services.system_setting_service import KEY_KB_EXTRACT_PROVIDER, update_settings


def test_adapt_docling_table_figure_equation():
    raw = [
        {"type": "paragraph", "text": "intro", "page": 1},
        {"type": "picture", "img_path": "figs/a.png", "caption": ["Fig 1"], "page_idx": 0},
        {"type": "table", "table_body": "|h|v|\n|--|--|", "caption": ["T1"], "page_no": 2},
        {"type": "formula", "latex": "E=mc^2", "page_idx": 1},
    ]
    adapted = adapt_docling_content_list(raw)
    assert len(adapted) == 4
    assert adapted[0]["type"] == "text" and adapted[0]["page_idx"] == 0
    assert adapted[1]["type"] == "image" and adapted[1]["image_caption"] == ["Fig 1"]
    assert adapted[2]["type"] == "table" and adapted[2]["page_idx"] == 1
    assert adapted[3]["type"] == "equation"


def test_adapt_docling_skip_image_without_path():
    assert adapt_docling_block({"type": "picture"}) is None


def test_docling_payload_with_content_list():
    data = {
        "markdown": "# doc",
        "content_list": [{"type": "table", "markdown": "|a|b|", "page_idx": 0}],
        "assets_dir": "/tmp/assets",
    }
    result = _parse_docling_payload(data)
    assert result.engine == "docling"
    assert result.content_list is not None
    assert result.content_list[0]["type"] == "table"
    assert result.mineru_assets_dir == "/tmp/assets"


def test_docling_markdown_only():
    result = _parse_docling_payload({"text": "plain"})
    assert result.content_list is None
    assert result.engine == "docling"


@patch("services.extract.providers.registry._legacy_extract")
def test_docling_fallback_engine_legacy(mock_legacy, db_session, regular_user, tmp_path):
    update_settings(db_session, {KEY_KB_EXTRACT_PROVIDER: "docling"})
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="a.pdf",
        original_name="a.pdf",
        file_path=str(pdf),
        file_size=4,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    mock_legacy.return_value = ExtractResult(text="legacy ok", engine="legacy")
    with patch(
        "services.extract.providers.docling_provider.extract_docling",
        side_effect=RuntimeError("docling down"),
    ):
        with patch("services.extract.providers.registry.logger") as mock_log:
            result = extract_with_provider(f, db_session)
    assert result.engine == "legacy"
    assert result.fallback_from == "docling"
    mock_legacy.assert_called_once()
    mock_log.warning.assert_called_once()
    assert "docling_fallback_reason=" in mock_log.warning.call_args[0][0]


@patch("services.extract.providers.docling_provider.DOCLING_URL", "http://docling.test")
@patch("httpx.Client")
def test_docling_sidecar_content_list(mock_client_cls, regular_user, tmp_path):
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
    mock_resp = mock_client_cls.return_value.__enter__.return_value.post.return_value
    mock_resp.raise_for_status = lambda: None
    mock_resp.json.return_value = {
        "markdown": "# md",
        "content_list": [
            {"type": "table", "table_body": "|x|y|\n|1|2|", "page_idx": 0},
            {"type": "figure", "img_path": "images/f.jpg", "page_idx": 0},
        ],
    }
    result = extract_docling(f)
    assert result.engine == "docling"
    assert len(result.content_list or []) == 2
    md = content_list_to_markdown(result.content_list or [])
    assert ContentKind.table.value in md
    assert ContentKind.figure.value in md


def test_docling_structured_persist(regular_user, tmp_path):
    from config import UPLOAD_DIR

    rel_dir = os.path.join(str(regular_user.id), "2026-06")
    user_dir = os.path.join(UPLOAD_DIR, rel_dir)
    os.makedirs(user_dir, exist_ok=True)
    pdf_path = os.path.join(user_dir, "docling.pdf")
    Path(pdf_path).write_bytes(b"%PDF-1.4")
    f = FileModel(
        filename="docling.pdf",
        original_name="docling.pdf",
        file_path=pdf_path,
        file_size=8,
        mime_type="application/pdf",
        user_id=regular_user.id,
    )
    f.id = 501
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "f.jpg").write_bytes(b"IMG")
    items = adapt_docling_content_list(
        [{"type": "image", "img_path": "f.jpg", "page_idx": 0, "caption": ["Fig"]}]
    )
    normalized = normalize_content_list_asset_paths(f, items, str(assets))
    md = prepare_structured_extract(f, items, str(assets))
    assert "filex:content" in md
    assert ".extract_assets/501/" in normalized[0]["img_path"]
    assert normalized[0]["img_path"] in md
