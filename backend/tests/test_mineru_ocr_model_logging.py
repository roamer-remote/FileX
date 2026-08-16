# Copyright (c) 2026 徐泽宇
"""Regression tests for task-level MinerU OCR model logging."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from pathlib import Path

SIDECAR_DIR = Path(__file__).resolve().parents[2] / "docker" / "mineru-sidecar"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))


def test_resolve_ocr_models_returns_selected_names_and_absolute_paths(tmp_path):
    from mineru_v4_runner import resolve_ocr_model_usage

    model_root = tmp_path / "models" / "PDF-Extract-Kit-1.0" / "models" / "OCR" / "paddleocr_torch"
    model_root.mkdir(parents=True)
    det = model_root / "ch_PP-OCRv6_small_det_infer.safetensors"
    rec = model_root / "ch_PP-OCRv6_small_rec_infer.safetensors"
    det.write_bytes(b"det")
    rec.write_bytes(b"rec")
    config = tmp_path / "models_config.yml"
    config.write_text(
        "lang:\n  ch:\n    det: ch_PP-OCRv6_small_det_infer.safetensors\n"
        "    rec: ch_PP-OCRv6_small_rec_infer.safetensors\n",
        encoding="utf-8",
    )
    usage = resolve_ocr_model_usage(
        "ch", config_path=config, model_dir=model_root, use_angle_cls=False
    )

    assert usage == [
        {
            "component": "ocr_det",
            "model_name": "ch_PP-OCRv6_small_det",
            "model_path": str(det.resolve()),
        },
        {
            "component": "ocr_rec",
            "model_name": "ch_PP-OCRv6_small_rec",
            "model_path": str(rec.resolve()),
        },
    ]


def test_write_ocr_model_usage_is_json_and_records_absolute_paths(tmp_path):
    from mineru_v4_runner import write_ocr_model_usage

    output = tmp_path / "out"
    output.mkdir()
    usage = [{"component": "ocr_det", "model_name": "det", "model_path": "/models/det"}]

    path = write_ocr_model_usage(output, usage)

    assert path == output / "mineru_ocr_model_usage.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"models": usage}


def test_runtime_ocr_model_usage_reads_weights_from_real_runtime_objects(tmp_path):
    from mineru_v4_runner import _runtime_ocr_model_usage

    class _Model:
        def __init__(self, path):
            self.weights_path = path

    class _Ocr:
        text_detector = _Model(tmp_path / "det_infer.pth")
        text_recognizer = _Model(tmp_path / "rec_infer.pth")

    usage = _runtime_ocr_model_usage(_Ocr())

    assert usage[0]["model_name"] == "det"
    assert usage[0]["model_path"] == str((tmp_path / "det_infer.pth").resolve())
    assert usage[1]["model_name"] == "rec"


def test_read_ocr_model_usage_logs_each_model(caplog, tmp_path):
    from mineru_runner import _log_ocr_model_usage, _read_ocr_model_usage

    usage_path = tmp_path / "mineru_ocr_model_usage.json"
    usage_path.write_text(
        json.dumps(
            {
                "models": [
                    {"component": "ocr_det", "model_name": "det", "model_path": "/models/det"},
                    {"component": "ocr_rec", "model_name": "rec", "model_path": "/models/rec"},
                ]
            }
        ),
        encoding="utf-8",
    )

    with caplog.at_level("INFO", logger="mineru_runner"):
        usage = _read_ocr_model_usage(tmp_path)
        _log_ocr_model_usage(usage)

    assert usage[0]["model_name"] == "det"
    assert any(
        "ocr_model component=ocr_det model_name=det model_path=/models/det" in r.message
        for r in caplog.records
    )
    assert any(
        "ocr_model component=ocr_rec model_name=rec model_path=/models/rec" in r.message
        for r in caplog.records
    )


def test_read_ocr_model_usage_ignores_relative_paths(tmp_path):
    from mineru_runner import _read_ocr_model_usage

    (tmp_path / "mineru_ocr_model_usage.json").write_text(
        json.dumps({"models": [{"component": "ocr_det", "model_name": "det", "model_path": "models/det"}]}),
        encoding="utf-8",
    )

    assert _read_ocr_model_usage(tmp_path) == []


def test_ocr_model_usage_is_encoded_in_extract_operation_log_fields():
    from services.kb_extract_service import _ocr_detail_fields

    result = SimpleNamespace(
        ocr_stats=None,
        ocr_model_usage=[
            {
                "component": "ocr_det",
                "model_name": "det",
                "model_path": "/models/det",
            },
            {
                "component": "ocr_rec",
                "model_name": "rec",
                "model_path": "/models/rec",
            },
        ],
    )

    assert _ocr_detail_fields(result) == {
        "ocr_model_ocr_det": "det",
        "ocr_model_path_ocr_det": "/models/det",
        "ocr_model_ocr_rec": "rec",
        "ocr_model_path_ocr_rec": "/models/rec",
    }
