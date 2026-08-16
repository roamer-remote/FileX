# Copyright (c) 2026 徐泽宇
"""070: Docling sidecar runner cache + timeout."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

SIDECAR_DIR = Path(__file__).resolve().parents[2] / "docker" / "docling-sidecar"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))

from docling_runner import run_docling_pipeline  # noqa: E402


@patch("docling_runner._convert_document")
def test_run_docling_pipeline_persists_payload(mock_convert, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setenv("DOCLING_CACHE_DIR", str(cache))
    monkeypatch.setenv("DOCLING_PARSE_TIMEOUT_SEC", "550")
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF-1.4")
    mock_convert.return_value = {
        "markdown": "# hello",
        "content_list": [{"type": "text", "text": "hi", "page_idx": 0}],
    }

    result = run_docling_pipeline(str(src), "doc.pdf", file_id=10, job_id=2)
    assert result["markdown"] == "# hello"
    payload_path = cache / "parse" / "f10_j2" / "out" / "payload.json"
    assert payload_path.is_file()
    saved = json.loads(payload_path.read_text(encoding="utf-8"))
    assert saved["markdown"] == "# hello"


@patch("docling_runner._convert_document")
def test_bypass_cache_skips_job_cache(mock_convert, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setenv("DOCLING_CACHE_DIR", str(cache))
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF-1.4")
    out_dir = cache / "parse" / "f5" / "out"
    out_dir.mkdir(parents=True)
    (out_dir / "payload.json").write_text(
        json.dumps({"markdown": "# cached"}),
        encoding="utf-8",
    )
    mock_convert.return_value = {"markdown": "# fresh", "content_list": []}

    result = run_docling_pipeline(str(src), "doc.pdf", file_id=5, bypass_cache=True)
    assert result["markdown"] == "# fresh"
    mock_convert.assert_called_once()
