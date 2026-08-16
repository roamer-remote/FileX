# Copyright (c) 2026 徐泽宇
"""070: Docling sidecar 050 contract."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from models.file import File as FileModel
from services.extract.providers.docling_provider import (
    DoclingRpcError,
    _docling_payload_from_rpc_reply,
    _parse_docling_payload,
    extract_docling,
)


def test_parse_docling_payload_requires_content():
    with pytest.raises(ValueError, match="空正文"):
        _parse_docling_payload({})


def test_docling_payload_from_rpc_reply_strips_ok():
    cleaned = _docling_payload_from_rpc_reply(
        {"ok": True, "markdown": "# hi", "correlation_id": "x"}
    )
    assert cleaned == {"markdown": "# hi"}


def test_docling_payload_from_rpc_reply_error():
    with pytest.raises(DoclingRpcError):
        _docling_payload_from_rpc_reply({"ok": False, "error": "fail"})


@patch("services.extract.providers.docling_provider.KB_EXTRACT_DOCLING_USE_MQ", False)
@patch("services.extract.providers.docling_provider.DOCLING_URL", "http://docling.test")
@patch("httpx.Client")
def test_http_extract_content_list(mock_client_cls, regular_user, tmp_path):
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
        "assets_dir": "/cache/out",
    }
    result = extract_docling(f)
    assert result.text == "# structured"
    assert result.content_list[0]["type"] == "table"
