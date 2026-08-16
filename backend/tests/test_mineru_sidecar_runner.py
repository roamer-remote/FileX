# Copyright (c) 2026 徐泽宇
"""032 PR-A: MinerU sidecar runner assets_dir persistence."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SIDECAR_DIR = Path(__file__).resolve().parents[2] / "docker" / "mineru-sidecar"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))

from mineru_runner import _run_mineru_subprocess, run_mineru_pipeline  # noqa: E402


def _fake_mineru_output(out_root: Path) -> None:
    doc_dir = out_root / "doc" / "auto"
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "doc.md").write_text("# hello", encoding="utf-8")
    cl = [{"type": "image", "img_path": "fig1.jpg", "page_idx": 0}]
    (doc_dir / "doc_content_list.json").write_text(json.dumps(cl), encoding="utf-8")
    (doc_dir / "fig1.jpg").write_bytes(b"fake-image")


@patch("mineru_runner.subprocess.run")
def test_persistent_finds_output_under_mineru_stem_auto(mock_run, tmp_path, monkeypatch):
    """MinerU CLI writes to out/{stem}/auto/ when -o is work/out."""
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "handbook.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        assert out_dir.name == "out"
        doc_dir = out_dir / "uuid_handbook" / "auto"
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / "uuid_handbook.md").write_text("# handbook", encoding="utf-8")
        cl = [{"type": "text", "page_idx": 0}]
        (doc_dir / "uuid_handbook_content_list.json").write_text(json.dumps(cl), encoding="utf-8")
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    result = run_mineru_pipeline(str(pdf), "handbook.pdf", file_id=242, job_id=264)
    assert result["markdown"] == "# handbook"
    assert result["content_list"] == [{"type": "text", "page_idx": 0}]


@patch("mineru_runner.subprocess.run")
def test_persistent_assets_dir_survives_parse(mock_run, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        assert out_dir.name == "out"
        _fake_mineru_output(out_dir)
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    result = run_mineru_pipeline(str(pdf), "sample.pdf", file_id=99, job_id=3)
    assets_dir = Path(result["assets_dir"])
    assert assets_dir.is_dir()
    assert (assets_dir / "fig1.jpg").is_file()
    assert result["markdown"] == "# hello"
    assert result.get("ok") is None


@patch("mineru_runner.subprocess.run")
def test_ephemeral_debug_run_cleans_temp(mock_run, tmp_path):
    pdf = tmp_path / "debug.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    seen_out: list[Path] = []

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_parent = Path(cmd[out_flag + 1])
        seen_out.append(out_parent)
        _fake_mineru_output(out_parent)
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    result = run_mineru_pipeline(str(pdf), "debug.pdf")
    assert "# hello" in result["markdown"]
    assert not seen_out[0].exists()


def test_copy_assets_recursive_images_subdir(tmp_path):
    from mineru_runner import _copy_assets_with_prefix, _rewrite_content_list_paths  # noqa: E402

    src = tmp_path / "auto"
    img = src / "images" / "hash.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"img-bytes")
    dest = tmp_path / "merged_assets"
    mapping = _copy_assets_with_prefix(src, dest, chunk_index=0)
    assert mapping["images/hash.jpg"] == "images/hash.jpg"
    assert (dest / "images" / "hash.jpg").is_file()

    cl = _rewrite_content_list_paths(
        [{"type": "image", "img_path": "images/hash.jpg", "page_idx": 1}],
        page_offset=48,
        asset_map=mapping,
    )
    assert cl[0]["page_idx"] == 49
    assert cl[0]["img_path"] == "images/hash.jpg"


@patch("mineru_runner.subprocess.run")
@patch("mineru_runner._pdf_page_count", return_value=100)
def test_page_chunks_merge_global_page_idx(mock_pages, mock_run, tmp_path, monkeypatch):
    from mineru_runner import _parse_runtime_config  # noqa: E402

    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "big.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    cfg = _parse_runtime_config(
        {
            "min_batch_mode": "auto",
            "min_batch_inference_size": 32,
            "min_batch_floor": 8,
            "parse_method": "auto",
            "formula_enable": True,
            "table_enable": True,
            "parse_timeout_sec": 850,
            "page_chunk_enabled": True,
            "page_chunk_threshold": 50,
            "page_chunk_pages": 48,
            "table_auto_rotate": False,
            "table_rotate_max_tables": 8,
            "table_rotate_timeout_sec": 30,
            "config_fingerprint": "abc123",
        }
    )
    call_idx = {"n": 0}

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        start = int(cmd[cmd.index("-s") + 1])
        doc_dir = out_dir / "doc" / "auto"
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / "doc.md").write_text(f"# chunk {call_idx['n']}", encoding="utf-8")
        cl = [{"type": "text", "page_idx": 0, "text": "hi"}]
        (doc_dir / "doc_content_list.json").write_text(json.dumps(cl), encoding="utf-8")
        call_idx["n"] += 1
        assert start in (0, 48, 96)
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    result = run_mineru_pipeline(
        str(pdf),
        "big.pdf",
        file_id=1,
        job_id=2,
        runtime_config={
            "min_batch_mode": cfg.min_batch_mode,
            "min_batch_inference_size": cfg.min_batch_inference_size,
            "min_batch_floor": cfg.min_batch_floor,
            "parse_method": cfg.parse_method,
            "formula_enable": cfg.formula_enable,
            "table_enable": cfg.table_enable,
            "parse_timeout_sec": cfg.parse_timeout_sec,
            "page_chunk_enabled": cfg.page_chunk_enabled,
            "page_chunk_threshold": cfg.page_chunk_threshold,
            "page_chunk_pages": cfg.page_chunk_pages,
            "table_auto_rotate": cfg.table_auto_rotate,
            "table_rotate_max_tables": cfg.table_rotate_max_tables,
            "table_rotate_timeout_sec": cfg.table_rotate_timeout_sec,
            "config_fingerprint": cfg.config_fingerprint,
        },
    )
    assert mock_run.call_count == 3
    assert result["content_list"][0]["page_idx"] == 0
    assert result["content_list"][-1]["page_idx"] == 96


@patch("mineru_runner.subprocess.run")
def test_chunk_progress_logs(mock_run, tmp_path, monkeypatch, caplog):
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        _fake_mineru_output(out_dir)
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    with caplog.at_level(logging.INFO, logger="mineru_runner"):
        run_mineru_pipeline(str(pdf), "sample.pdf", file_id=10, job_id=11)

    messages = [r.getMessage() for r in caplog.records if r.name == "mineru_runner"]
    assert any("mineru chunk start" in m for m in messages)
    assert any("mineru chunk done" in m and "ok=True" in m for m in messages)


@patch("mineru_runner.subprocess.run")
def test_gpu_parse_failure_never_retries_with_cpu(mock_run, tmp_path):
    output_dir = tmp_path / "out"
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="CUDA kernel failed")

    with pytest.raises(RuntimeError, match="CPU fallback is disabled"):
        _run_mineru_subprocess(
            ["python3", "runner.py", "-o", str(output_dir)],
            env={"MINERU_DEVICE": "cuda", "CUDA_VISIBLE_DEVICES": "0"},
            timeout_sec=10,
            out_dir=output_dir,
        )

    mock_run.assert_called_once()


@patch("mineru_runner.subprocess.Popen")
def test_log_cli_streams_to_logger(mock_popen, tmp_path, monkeypatch, caplog):
    cache = tmp_path / "cache"
    monkeypatch.setenv("MINERU_CACHE_DIR", str(cache))
    monkeypatch.setenv("MINERU_LOG_CLI", "1")
    pdf = tmp_path / "cli.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    out_holder: list[Path] = []

    class _FakeStdout:
        def __iter__(self):
            yield "layout pass 1/3\n"
            yield "ocr page 12\n"

        def readline(self):
            return ""

    class _FakeProc:
        def __init__(self, cmd, **kwargs):
            out_flag = cmd.index("-o")
            out_holder.append(Path(cmd[out_flag + 1]))
            self.stdout = _FakeStdout()
            self._rc = 0

        def wait(self, timeout=None):
            _fake_mineru_output(out_holder[0])
            return self._rc

        def kill(self):
            pass

    mock_popen.side_effect = _FakeProc

    with caplog.at_level(logging.INFO, logger="mineru_runner"):
        run_mineru_pipeline(str(pdf), "cli.pdf", file_id=12, job_id=13)

    cli_lines = [r.getMessage() for r in caplog.records if "mineru cli |" in r.getMessage()]
    assert any("layout pass" in m for m in cli_lines)
    cli_log = out_holder[0] / "mineru.cli.log"
    assert cli_log.is_file()
    assert "layout pass" in cli_log.read_text(encoding="utf-8")
