# Copyright (c) 2026 徐泽宇
"""050 SC-050-005/006: table auto-rotation golden + fail-open."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SIDECAR_DIR = Path(__file__).resolve().parents[2] / "docker" / "mineru-sidecar"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))

from table_rotation import (  # noqa: E402
    choose_best_rotation,
    inject_rotation_meta,
    is_table_auto_rotate_enabled,
    preprocess_pdf_tables,
    RotationRecord,
)
from mineru_runner import run_mineru_pipeline  # noqa: E402

FIXTURE_PDF = Path(__file__).resolve().parent / "fixtures" / "pdf" / "table_rotated_90.pdf"
FIXTURE_HEADER = "FIXTURE_HEADER_ALPHA"


def test_rotation_default_disabled(monkeypatch):
    monkeypatch.delenv("KB_EXTRACT_TABLE_AUTO_ROTATE", raising=False)
    assert is_table_auto_rotate_enabled() is False


def test_choose_best_rotation_picks_highest_score():
    from PIL import Image

    img = Image.new("RGB", (120, 80), color=(255, 255, 255))
    call = {"i": 0}
    order = (0, 90, 180, 270)
    scores = {0: 10.0, 90: 90.0, 180: 20.0, 270: 15.0}

    def ocr_fn(_image):
        angle = order[call["i"]]
        call["i"] += 1
        return scores[angle]

    angle, score = choose_best_rotation(img, ocr_fn=ocr_fn, timeout_sec=5)
    assert angle == 90
    assert score == 90.0


def test_inject_rotation_meta_on_table_blocks():
    payload = {
        "markdown": "md",
        "content_list": [{"type": "table", "table_body": "|a|", "page_idx": 0}],
    }
    records = [RotationRecord(page_idx=0, rotation=90)]
    out = inject_rotation_meta(payload, records)
    assert out["content_list"][0]["rotation_applied"] == 90
    assert out["table_rotation_debug"][0]["rotation_applied"] == 90


def test_inject_rotation_meta_multi_page():
    payload = {
        "markdown": "md",
        "content_list": [
            {"type": "table", "table_body": "|p0|", "page_idx": 0},
            {"type": "table", "table_body": "|p1|", "page_idx": 1},
            {"type": "text", "text": "body", "page_idx": 1},
        ],
    }
    records = [
        RotationRecord(page_idx=0, rotation=90),
        RotationRecord(page_idx=1, rotation=180),
    ]
    out = inject_rotation_meta(payload, records)
    assert out["content_list"][0]["rotation_applied"] == 90
    assert out["content_list"][1]["rotation_applied"] == 180
    assert "rotation_applied" not in out["content_list"][2]
    assert len(out["table_rotation_debug"]) == 2
    assert {d["page_idx"] for d in out["table_rotation_debug"]} == {0, 1}


def test_preprocess_fail_open_returns_original(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_EXTRACT_TABLE_AUTO_ROTATE", "1")
    src = FIXTURE_PDF
    out, records = preprocess_pdf_tables(src, tmp_path / "rotate", ocr_fn=lambda _img: 0.0)
    assert out == src
    assert records == []


def test_preprocess_deterministic_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_EXTRACT_TABLE_AUTO_ROTATE", "1")
    with patch("table_rotation.choose_best_rotation", return_value=(90, 85.0)):
        out, records = preprocess_pdf_tables(FIXTURE_PDF, tmp_path / "rotate")
    assert records
    assert records[0].rotation == 90
    assert out.suffix == ".pdf"
    assert out != FIXTURE_PDF


def test_preprocess_with_mock_ocr_rotates(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_EXTRACT_TABLE_AUTO_ROTATE", "1")
    monkeypatch.setenv("KB_EXTRACT_TABLE_ROTATE_MAX_TABLES", "2")

    def ocr_fn(image):
        from PIL import Image

        if not isinstance(image, Image.Image):
            return 0.0
        return 85.0 if image.width >= image.height else 5.0

    out, records = preprocess_pdf_tables(FIXTURE_PDF, tmp_path / "rotate2", ocr_fn=ocr_fn)
    if records:
        assert any(r.rotation == 90 for r in records)
        assert out.suffix == ".pdf"
    else:
        pytest.skip("OCR heuristic did not detect rotation on this platform")


@patch("mineru_runner.subprocess.run")
def test_runner_injects_rotation_debug(mock_run, tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KB_EXTRACT_TABLE_AUTO_ROTATE", "0")

    pdf = FIXTURE_PDF
    assert pdf.is_file()

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        doc_dir = out_dir / "doc" / "auto"
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / "doc.md").write_text(f"# table\n{FIXTURE_HEADER}", encoding="utf-8")
        cl = [{"type": "table", "table_body": f"|{FIXTURE_HEADER}|", "page_idx": 0}]
        (doc_dir / "doc_content_list.json").write_text(json.dumps(cl), encoding="utf-8")
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    with patch("table_rotation.preprocess_pdf_tables", return_value=(pdf, [RotationRecord(0, 90)])):
        result = run_mineru_pipeline(str(pdf), "table_rotated_90.pdf", file_id=1, job_id=2)

    assert FIXTURE_HEADER in result["markdown"]
    assert result["content_list"][0].get("rotation_applied") == 90
    assert result.get("table_rotation_debug")


@patch("mineru_runner.subprocess.run")
def test_rotation_timeout_fail_open(mock_run, tmp_path, monkeypatch):
    monkeypatch.setenv("MINERU_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KB_EXTRACT_TABLE_AUTO_ROTATE", "1")
    monkeypatch.setenv("KB_EXTRACT_TABLE_ROTATE_TIMEOUT_SEC", "0.01")

    def slow_ocr(_img):
        import time

        time.sleep(2)
        return 1.0

    def _run(cmd, **kwargs):
        out_flag = cmd.index("-o")
        out_dir = Path(cmd[out_flag + 1])
        doc_dir = out_dir / "doc" / "auto"
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / "doc.md").write_text("# ok", encoding="utf-8")
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run

    with patch("table_rotation._default_ocr_confidence", side_effect=slow_ocr):
        result = run_mineru_pipeline(str(FIXTURE_PDF), "table_rotated_90.pdf", file_id=3, job_id=4)

    assert result["markdown"] == "# ok"
