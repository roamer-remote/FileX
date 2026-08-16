# Copyright (c) 2026 徐泽宇
"""033: MinerU sidecar parse cache hit and elapsed logging."""

from __future__ import annotations

import json
import logging
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


@patch("mineru_runner.subprocess.run")
def test_cache_hit_skips_subprocess(mock_run, tmp_path, monkeypatch, caplog):
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    out_root = cache / "parse" / "f10_j20" / "out"
    _seed_parse_cache(out_root)

    with caplog.at_level(logging.INFO, logger="mineru_runner"):
        result = run_mineru_pipeline(str(pdf), "sample.pdf", file_id=10, job_id=20)
    assert result["markdown"] == "# cached doc"
    mock_run.assert_not_called()

    done_logs = [r for r in caplog.records if "mineru parse done" in r.getMessage()]
    assert len(done_logs) == 1
    msg = done_logs[0].getMessage()
    assert "cache_hit=True" in msg
    assert "cache_tier=job" in msg
    assert "received_at=" in msg
    assert "finished_at=" in msg
    assert "elapsed_sec=" in msg


@patch("mineru_runner.subprocess.run")
def test_cli_path_logs_elapsed_sec(mock_run, tmp_path, monkeypatch, caplog):
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "run.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        _seed_parse_cache(out_dir)
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    with caplog.at_level(logging.INFO, logger="mineru_runner"):
        run_mineru_pipeline(str(pdf), "run.pdf", file_id=11, job_id=21)

    done_logs = [r for r in caplog.records if "mineru parse done" in r.getMessage()]
    assert len(done_logs) == 1
    msg = done_logs[0].getMessage()
    assert "cache_hit=False" in msg
    assert "ok=True" in msg
    assert "received_at=" in msg
    assert "finished_at=" in msg
    assert "elapsed_sec=" in msg
    mock_run.assert_called_once()


@patch("mineru_runner.subprocess.run")
def test_invalid_cache_rmtree_then_cli(mock_run, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    work = cache / "parse" / "f12_j22"
    out_root = work / "out"
    out_root.mkdir(parents=True)
    (out_root / "partial.txt").write_text("not mineru output", encoding="utf-8")

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        _seed_parse_cache(out_dir)
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    result = run_mineru_pipeline(str(pdf), "bad.pdf", file_id=12, job_id=22)
    assert result["markdown"] == "# cached doc"
    mock_run.assert_called_once()
