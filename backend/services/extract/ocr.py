# Copyright (c) 2026 徐泽宇
"""OCR via rapidocr-onnxruntime; optional Paddle if KB_OCR_ENGINE=paddle.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from config import KB_OCR_ENGINE

logger = logging.getLogger(__name__)

_rapid_engine: Any = None


def _rapid_ocr() -> Any:
    global _rapid_engine
    if _rapid_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _rapid_engine = RapidOCR()
    return _rapid_engine


def _paddle_ocr() -> Any:
    from paddleocr import PaddleOCR

    return PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)


def ocr_image_bytes(image_bytes: bytes) -> str:
    if not image_bytes:
        return ""
    from services.extract.ocr_preprocess import maybe_preprocess_image_bytes

    image_bytes = maybe_preprocess_image_bytes(image_bytes)
    return _ocr_raw_image_bytes(image_bytes)


def _rapid_ocr_lines_and_confidence(image_bytes: bytes) -> tuple[str, float | None]:
    engine = _rapid_ocr()
    result, _ = engine(image_bytes)
    if not result:
        return "", None
    lines: list[str] = []
    confidences: list[float] = []
    for item in result:
        if not item or len(item) < 2:
            continue
        lines.append(str(item[1]))
        if len(item) >= 3 and item[2] is not None:
            try:
                confidences.append(float(item[2]))
            except (TypeError, ValueError):
                continue
    text = "\n".join(lines).strip()
    if not confidences:
        return text, None
    return text, round(sum(confidences) / len(confidences), 4)


def _ocr_raw_with_confidence(image_bytes: bytes) -> tuple[str, float | None]:
    if KB_OCR_ENGINE == "paddle":
        try:
            import cv2

            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return "", None
            ocr = _paddle_ocr()
            lines = ocr.ocr(img, cls=True)
            parts: list[str] = []
            for block in lines or []:
                for line in block or []:
                    if line and len(line) >= 2 and line[1]:
                        parts.append(str(line[1][0]))
            return "\n".join(parts).strip(), None
        except Exception:
            logger.exception("paddle OCR failed, falling back to rapid")
    return _rapid_ocr_lines_and_confidence(image_bytes)


def _ocr_raw_image_bytes(image_bytes: bytes) -> str:
    text, _ = _ocr_raw_with_confidence(image_bytes)
    return text


def ocr_pil_image(img: Any) -> str:
    text, _ = ocr_pil_image_with_confidence(img)
    return text


def ocr_pil_image_with_confidence(img: Any) -> tuple[str, float | None]:
    from services.extract.ocr_preprocess import preprocess_pil_image

    img = preprocess_pil_image(img)
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return _ocr_raw_with_confidence(buf.getvalue())


def _polygon_to_bbox(polygon: Any) -> list[float]:
    """LiteParse OCR API: axis-aligned [x1, y1, x2, y2]."""
    if isinstance(polygon, (list, tuple)) and len(polygon) == 4:
        if all(isinstance(x, (int, float)) for x in polygon):
            return [float(polygon[0]), float(polygon[1]), float(polygon[2]), float(polygon[3])]
    xs: list[float] = []
    ys: list[float] = []
    for point in polygon or []:
        if point and len(point) >= 2:
            xs.append(float(point[0]))
            ys.append(float(point[1]))
    if not xs:
        return [0.0, 0.0, 0.0, 0.0]
    return [min(xs), min(ys), max(xs), max(ys)]


def _image_size(image_bytes: bytes) -> tuple[int, int]:
    import io

    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as img:
        return img.size


def ocr_image_bytes_for_liteparse(
    image_bytes: bytes,
    *,
    language: str | None = None,
) -> list[dict[str, object]]:
    """Return LiteParse OCR API results: text, bbox, confidence."""
    del language  # RapidOCR 默认中英；保留参数以符合 /ocr 契约
    if not image_bytes:
        return []
    from services.extract.ocr_preprocess import maybe_preprocess_image_bytes

    image_bytes = maybe_preprocess_image_bytes(image_bytes)
    width, height = _image_size(image_bytes)
    fallback_bbox = [0.0, 0.0, float(width), float(height)]

    if KB_OCR_ENGINE == "paddle":
        text = _ocr_raw_image_bytes(image_bytes)
        if not text.strip():
            return []
        return [{"text": text, "bbox": fallback_bbox, "confidence": 1.0}]

    engine = _rapid_ocr()
    result, _ = engine(image_bytes)
    if not result:
        return []

    items: list[dict[str, object]] = []
    for row in result:
        if not row or len(row) < 2:
            continue
        box = row[0]
        text = str(row[1]).strip()
        if not text:
            continue
        conf = 1.0
        if len(row) >= 3 and row[2] is not None:
            try:
                conf = float(row[2])
            except (TypeError, ValueError):
                conf = 1.0
        bbox = _polygon_to_bbox(box)
        if bbox == [0.0, 0.0, 0.0, 0.0]:
            bbox = fallback_bbox
        items.append(
            {
                "text": text,
                "bbox": bbox,
                "confidence": min(1.0, max(0.0, conf)),
            },
        )
    return items
