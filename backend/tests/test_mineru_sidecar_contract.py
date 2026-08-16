# Copyright (c) 2026 徐泽宇
"""032 PR-A: MinerU sidecar 030 contract."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from models.file import File as FileModel
from services.extract.providers.mineru_provider import _parse_sidecar_payload, extract_mineru


def test_parse_sidecar_payload_requires_content():
    with pytest.raises(ValueError, match="空正文"):
        _parse_sidecar_payload({})


def test_parse_sidecar_prefers_markdown_over_text():
    r = _parse_sidecar_payload({"markdown": "# md", "text": "plain"})
    assert r.text == "# md"


def test_parse_sidecar_preserves_ocr_model_usage():
    r = _parse_sidecar_payload(
        {
            "markdown": "# md",
            "ocr_model_usage": [
                {
                    "component": "ocr_det",
                    "model_name": "det",
                    "model_path": "/models/det",
                }
            ],
        }
    )
    assert r.ocr_model_usage == [
        {
            "component": "ocr_det",
            "model_name": "det",
            "model_path": "/models/det",
        }
    ]


def test_parse_sidecar_filters_malformed_ocr_model_usage():
    r = _parse_sidecar_payload(
        {
            "markdown": "# md",
            "ocr_model_usage": [
                {"component": "ocr_det", "model_name": "", "model_path": "/models/det"},
                "not-a-model",
            ],
        }
    )
    assert r.ocr_model_usage is None


@patch("services.extract.providers.mineru_provider.KB_EXTRACT_MINERU_USE_MQ", False)
@patch("services.extract.providers.mineru_provider.MINERU_URL", "http://mineru.test")
@patch("httpx.Client")
def test_http_extract_markdown_field(mock_client_cls, regular_user, tmp_path):
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
    mock_resp.json.return_value = {
        "markdown": "# structured",
        "content_list": [{"type": "table", "table_body": "|a|", "page_idx": 0}],
        "assets_dir": "/data/out",
    }
    result = extract_mineru(f)
    assert result.text == "# structured"
    assert result.content_list[0]["type"] == "table"
