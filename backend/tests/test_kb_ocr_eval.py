# Copyright (c) 2026 徐泽宇
"""103 P2: kb_ocr_eval script tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
GOLDEN_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "ocr_golden"


def _load_eval_module():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import kb_ocr_eval

    return kb_ocr_eval


def test_kb_ocr_eval_cer():
    mod = _load_eval_module()
    assert mod.cer("hello", "hello") == 0.0
    assert mod.cer("abcd", "abc") == 0.25


def test_kb_ocr_eval_script_runs(monkeypatch):
    mod = _load_eval_module()
    monkeypatch.setattr(mod, "_run_ocr", lambda _path: "OCR GOLDEN")
    rows = mod.evaluate_fixture_dir(GOLDEN_DIR)
    assert rows
    assert rows[0][0] == "sample.png"
    assert rows[0][1] == 0.0


def test_kb_ocr_eval_main_exit_zero(monkeypatch, capsys):
    mod = _load_eval_module()
    monkeypatch.setattr(mod, "_run_ocr", lambda _path: "OCR GOLDEN")
    monkeypatch.setattr(
        sys,
        "argv",
        ["kb_ocr_eval.py", "--fixture", str(GOLDEN_DIR)],
    )
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "CER" in out
    assert "sample.png" in out
