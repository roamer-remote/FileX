# Copyright (c) 2026 徐泽宇
"""040: MinerU bypass_cache skips content cache."""

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


@patch("mineru_runner.subprocess.run")
def test_bypass_cache_skips_content_hit(mock_run, tmp_path, monkeypatch, caplog):
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 bypass")

    md5 = hashlib.md5(pdf.read_bytes()).hexdigest()
    _seed_parse_cache(cache / "content" / md5 / "out")

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        _seed_parse_cache(out_dir)
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    with caplog.at_level(logging.INFO, logger="mineru_runner"):
        result = run_mineru_pipeline(
            str(pdf),
            "sample.pdf",
            file_id=10,
            job_id=20,
            bypass_cache=True,
        )

    assert result["markdown"] == "# cached doc"
    mock_run.assert_called_once()
    done = [r for r in caplog.records if "mineru parse done" in r.getMessage()][-1].getMessage()
    assert "cache_tier=none" in done
    assert "cache_hit=False" in done
