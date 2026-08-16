# Copyright (c) 2026 徐泽宇
"""Compatibility runner for MinerU 4 local Hybrid parsing.

MinerU 4's ``mineru`` command is a DocLib client and no longer accepts the
legacy local-pipeline flags. FileX invokes the bundled local API directly while
retaining the established output layout consumed by the sidecar.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def _model_name(filename: str) -> str:
    return Path(filename).stem.removesuffix("_infer")


def resolve_ocr_model_usage(
    lang: str,
    *,
    config_path: Path | None = None,
    model_dir: Path | None = None,
    use_angle_cls: bool = False,
) -> list[dict[str, str]]:
    """Resolve the OCR weights selected by MinerU's own pipeline config.

    This intentionally follows ``PytorchPaddleOCR``'s model selection rather
    than scanning the model directory, so the log describes the weights this
    parse invocation will pass to the OCR runtime.
    """
    if config_path is None:
        from mineru.model.ocr.pytorch_paddle import root_dir

        config_path = Path(root_dir) / "pytorchocr" / "utils" / "resources" / "models_config.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    params: dict[str, Any] = (config.get("lang") or {}).get(lang) or {}
    if not params:
        raise ValueError(f"MinerU OCR language is not configured: {lang}")

    if model_dir is None:
        from mineru.utils.model_registry import PDF_EXTRACT_KIT

        model_dir = PDF_EXTRACT_KIT.pytorch_paddle.local_dir()
    model_dir = model_dir.resolve()
    usage = []
    for component, key in (("ocr_det", "det"), ("ocr_rec", "rec")):
        filename = str(params[key])
        path = (model_dir / filename).resolve()
        usage.append(
            {
                "component": component,
                "model_name": _model_name(filename),
                "model_path": str(path),
            }
        )
    if use_angle_cls:
        # The current FileX pipeline leaves angle classification disabled. If
        # MinerU enables it in a future release, fail loudly until its actual
        # configured weight can be captured instead of logging a guess.
        raise ValueError("OCR angle classification model logging is not configured")
    return usage


def _runtime_ocr_model_usage(ocr: Any) -> list[dict[str, str]]:
    usage: list[dict[str, str]] = []
    for component, attr in (("ocr_det", "text_detector"), ("ocr_rec", "text_recognizer")):
        model = getattr(ocr, attr, None)
        model_path = getattr(model, "weights_path", None)
        if not model_path:
            continue
        path = str(Path(model_path).resolve())
        usage.append(
            {
                "component": component,
                "model_name": _model_name(path),
                "model_path": path,
            }
        )
    return usage


def install_ocr_model_usage_hook(output_dir: Path) -> None:
    """Capture weights after MinerU has constructed its real OCR runtime."""
    from mineru.model.ocr import pytorch_paddle

    original_init = pytorch_paddle.PytorchPaddleOCR.__init__

    def _init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        usage = _runtime_ocr_model_usage(self)
        if usage:
            write_ocr_model_usage(output_dir, usage)

    pytorch_paddle.PytorchPaddleOCR.__init__ = _init


def write_ocr_model_usage(output_dir: Path, usage: list[dict[str, str]]) -> Path:
    path = output_dir / "mineru_ocr_model_usage.json"
    path.write_text(json.dumps({"models": usage}, ensure_ascii=False), encoding="utf-8")
    return path

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-p", "--path", required=True)
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("-m", "--method", choices=("auto", "txt", "ocr"), default="auto")
    parser.add_argument("-s", "--start-page", type=int)
    parser.add_argument("-e", "--end-page", type=int)
    return parser.parse_args()


def main() -> None:
    from mineru.cli_old.common import do_parse

    args = _parse_args()
    source = Path(args.path)
    if args.method != "txt":
        install_ocr_model_usage_hook(Path(args.output))
    do_parse(
        str(Path(args.output)),
        [source.stem],
        [source.read_bytes()],
        ["ch"],
        backend="pipeline",
        parse_method=args.method,
        f_draw_layout_bbox=False,
        f_draw_span_bbox=False,
        f_dump_md=True,
        f_dump_middle_json=True,
        f_dump_model_output=False,
        f_dump_orig_pdf=False,
        f_dump_content_list=True,
        start_page_id=args.start_page or 0,
        end_page_id=args.end_page,
    )


if __name__ == "__main__":
    main()
