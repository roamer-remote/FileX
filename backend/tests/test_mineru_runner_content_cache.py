# Copyright (c) 2026 徐泽宇
"""040: MinerU sidecar content-level parse cache."""

from __future__ import annotations

import hashlib
import logging
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SIDECAR_DIR = Path(__file__).resolve().parents[2] / "docker" / "mineru-sidecar"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))

from mineru_runner import run_mineru_pipeline  # noqa: E402


def _seed_parse_cache(out_root: Path) -> None:
    doc_dir = out_root / "doc" / "auto"
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "doc.md").write_text("# cached doc", encoding="utf-8")
    cl = [{"type": "text", "page_idx": 0}]
    (doc_dir / "doc_content_list.json").write_text(json.dumps(cl), encoding="utf-8")


def _pdf_md5(pdf: Path) -> str:
    return hashlib.md5(pdf.read_bytes()).hexdigest()


@patch("mineru_runner.subprocess.run")
def test_content_cache_hit_new_job_id(mock_run, tmp_path, monkeypatch, caplog):
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 content")

    md5 = _pdf_md5(pdf)
    content_out = cache / "content" / md5 / "out"
    _seed_parse_cache(content_out)

    with caplog.at_level(logging.INFO, logger="mineru_runner"):
        result = run_mineru_pipeline(str(pdf), "sample.pdf", file_id=99, job_id=501)

    assert result["markdown"] == "# cached doc"
    mock_run.assert_not_called()
    done = [r for r in caplog.records if "mineru parse done" in r.getMessage()][0].getMessage()
    assert "cache_tier=content" in done
    assert "cache_hit=True" in done


@patch("mineru_runner.subprocess.run")
def test_promote_to_content_cache_after_cli(mock_run, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "run.pdf"
    pdf.write_bytes(b"%PDF-1.4 promote")

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        _seed_parse_cache(out_dir)
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    run_mineru_pipeline(str(pdf), "run.pdf", file_id=11, job_id=21)
    md5 = _pdf_md5(pdf)
    meta = cache / "content" / md5 / "meta.json"
    assert meta.is_file()
    assert json.loads(meta.read_text())["md5"] == md5
    assert (cache / "content" / md5 / "out" / "doc" / "auto" / "doc.md").is_file()


@patch("mineru_runner.subprocess.run")
def test_invalid_content_cache_rmtree_then_cli(mock_run, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(b"%PDF-1.4 bad")

    md5 = _pdf_md5(pdf)
    invalid_out = cache / "content" / md5 / "out"
    invalid_out.mkdir(parents=True)
    (invalid_out / "partial.txt").write_text("not mineru output", encoding="utf-8")

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        _seed_parse_cache(out_dir)
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    result = run_mineru_pipeline(str(pdf), "bad.pdf", file_id=12, job_id=22)
    assert result["markdown"] == "# cached doc"
    mock_run.assert_called_once()


@patch("mineru_runner.subprocess.run")
def test_content_cache_miss_legacy_meta_without_fingerprint(mock_run, tmp_path, monkeypatch, caplog):
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "legacy.pdf"
    pdf.write_bytes(b"%PDF-1.4 legacy cache")

    md5 = _pdf_md5(pdf)
    content_out = cache / "content" / md5 / "out"
    _seed_parse_cache(content_out)
    meta_path = cache / "content" / md5 / "meta.json"
    meta_path.write_text(json.dumps({"md5": md5, "size": 1}), encoding="utf-8")

    runtime_config = {
        "min_batch_mode": "auto",
        "min_batch_inference_size": 32,
        "min_batch_floor": 8,
        "parse_method": "auto",
        "formula_enable": True,
        "table_enable": True,
        "parse_timeout_sec": 850,
        "page_chunk_enabled": True,
        "page_chunk_threshold": 120,
        "page_chunk_pages": 48,
        "table_auto_rotate": False,
        "table_rotate_max_tables": 8,
        "table_rotate_timeout_sec": 30,
        "config_fingerprint": "newfp16hexchars",
    }

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        _seed_parse_cache(out_dir)
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    with caplog.at_level(logging.INFO, logger="mineru_runner"):
        result = run_mineru_pipeline(
            str(pdf),
            "legacy.pdf",
            file_id=20,
            job_id=30,
            runtime_config=runtime_config,
        )

    assert "cache miss fingerprint" in caplog.text
    mock_run.assert_called()
    assert result["markdown"] == "# cached doc"
