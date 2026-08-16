# Copyright (c) 2026 徐泽宇
"""Table auto-rotation pre-parse hook for filex-mineru (050)."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

OCRSnippetFn = Callable[["object"], float]
_OCR_BACKEND_WARNED = False


def _ocr_backend_available() -> bool:
    """Return True when pytesseract + tesseract-ocr are usable."""
    global _OCR_BACKEND_WARNED
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception as exc:
        if is_table_auto_rotate_enabled() and not _OCR_BACKEND_WARNED:
            logger.warning(
                "table rotation requires pytesseract and tesseract-ocr — OCR unavailable: %s",
                exc,
            )
            _OCR_BACKEND_WARNED = True
        return False


@dataclass(frozen=True)
class RotationRecord:
    page_idx: int
    rotation: int
    bbox: tuple[float, float, float, float] | None = None


def is_table_auto_rotate_enabled() -> bool:
    return (os.environ.get("KB_EXTRACT_TABLE_AUTO_ROTATE") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def max_tables_per_pdf() -> int:
    return max(1, int(os.environ.get("KB_EXTRACT_TABLE_ROTATE_MAX_TABLES") or "8"))


def rotate_timeout_sec() -> float:
    return max(1.0, float(os.environ.get("KB_EXTRACT_TABLE_ROTATE_TIMEOUT_SEC") or "30"))


def _default_ocr_confidence(image) -> float:
    if not _ocr_backend_available():
        return 0.0
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return 0.0
    if not isinstance(image, Image.Image):
        return 0.0
    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        confs = [float(c) for c in data.get("conf", []) if str(c).lstrip("-").isdigit() and float(c) >= 0]
        if not confs:
            return 0.0
        return sum(confs) / len(confs)
    except Exception as exc:
        logger.debug("table rotation OCR failed: %s", exc)
        return 0.0


def choose_best_rotation(
    image,
    ocr_fn: OCRSnippetFn | None = None,
    *,
    timeout_sec: float | None = None,
    angles: tuple[int, ...] = (0, 90, 180, 270),
) -> tuple[int, float]:
    from PIL import Image

    if not isinstance(image, Image.Image):
        return 0, 0.0
    fn = ocr_fn or _default_ocr_confidence
    deadline = time.monotonic() + (timeout_sec if timeout_sec is not None else rotate_timeout_sec())
    best_angle = 0
    best_score = -1.0
    for angle in angles:
        if time.monotonic() > deadline:
            logger.warning("table rotation timed out during angle scan")
            break
        rotated = image.rotate(-angle, expand=True) if angle else image
        score = fn(rotated)
        if score > best_score:
            best_score = score
            best_angle = angle
    return best_angle, max(best_score, 0.0)


def _detect_table_bboxes(page, *, max_tables: int) -> list[tuple[float, float, float, float]]:
    bboxes: list[tuple[float, float, float, float]] = []
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []
    rect = page.rect
    for d in drawings:
        r = d.get("rect")
        if r is None:
            continue
        w = abs(r.x1 - r.x0)
        h = abs(r.y1 - r.y0)
        if w * h < rect.width * rect.height * 0.05:
            continue
        bboxes.append((r.x0, r.y0, r.x1, r.y1))
        if len(bboxes) >= max_tables:
            return bboxes
    if not bboxes:
        margin = 0.05
        bboxes.append(
            (
                rect.width * margin,
                rect.height * margin,
                rect.width * (1 - margin),
                rect.height * (1 - margin),
            )
        )
    return bboxes[:max_tables]


def preprocess_pdf_tables(
    src: Path,
    work_dir: Path,
    *,
    ocr_fn: OCRSnippetFn | None = None,
) -> tuple[Path, list[RotationRecord]]:
    if not is_table_auto_rotate_enabled():
        return src, []
    if src.suffix.lower() != ".pdf":
        return src, []
    if ocr_fn is None:
        _ocr_backend_available()
    try:
        import fitz
        from PIL import Image
    except ImportError as exc:
        logger.warning("table rotation skipped (missing deps): %s", exc)
        return src, []

    work_dir.mkdir(parents=True, exist_ok=True)
    records: list[RotationRecord] = []
    try:
        doc = fitz.open(str(src))
    except Exception as exc:
        logger.warning("table rotation skipped (open pdf): %s", exc)
        return src, []

    try:
        max_tables = max_tables_per_pdf()
        per_table_timeout = rotate_timeout_sec()
        changed = False
        for page_idx in range(len(doc)):
            if len(records) >= max_tables:
                break
            page = doc[page_idx]
            bboxes = _detect_table_bboxes(page, max_tables=max_tables - len(records))
            for bbox in bboxes:
                if len(records) >= max_tables:
                    break
                mat = fitz.Matrix(2, 2)
                clip = fitz.Rect(*bbox)
                pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                angle, score = choose_best_rotation(
                    image,
                    ocr_fn=ocr_fn,
                    timeout_sec=per_table_timeout,
                )
                if angle == 0 or score <= 0:
                    continue
                records.append(RotationRecord(page_idx=page_idx, rotation=angle, bbox=bbox))
                changed = True
                logger.info(
                    "table rotation page=%s angle=%s score=%.1f bbox=%s",
                    page_idx,
                    angle,
                    score,
                    bbox,
                )
                import io

                rotated = image.rotate(-angle, expand=True)
                buf = io.BytesIO()
                rotated.save(buf, format="PNG")
                page.insert_image(clip, stream=buf.getvalue(), keep_proportion=False, overlay=True)

        if not changed:
            return src, records

        out_path = work_dir / f"{src.stem}.rotated.pdf"
        doc.save(str(out_path))
        return out_path, records
    except Exception as exc:
        logger.warning("table rotation fail-open: %s", exc)
        return src, records
    finally:
        doc.close()


def inject_rotation_meta(payload: dict, records: list[RotationRecord]) -> dict:
    if not records:
        return payload
    by_page: dict[int, int] = {}
    for rec in records:
        by_page.setdefault(rec.page_idx, rec.rotation)
    content_list = payload.get("content_list")
    if isinstance(content_list, list):
        for item in content_list:
            if not isinstance(item, dict):
                continue
            if (item.get("type") or "").strip().lower() != "table":
                continue
            try:
                page_idx = int(item.get("page_idx", 0))
            except (TypeError, ValueError):
                page_idx = 0
            rot = by_page.get(page_idx)
            if rot:
                item["rotation_applied"] = rot
    payload["table_rotation_debug"] = [
        {"page_idx": r.page_idx, "rotation_applied": r.rotation, "bbox": r.bbox} for r in records
    ]
    return payload
