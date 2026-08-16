"""High-confidence native-text PDF fast path backed by pdf-inspector."""

from __future__ import annotations

import logging
import multiprocessing
import os
from dataclasses import dataclass
from typing import Any

from config import (
    KB_EXTRACT_MAX_PAGES,
    KB_PDF_INSPECTOR_MIN_CONFIDENCE,
    KB_PDF_INSPECTOR_TIMEOUT_SEC,
)
from services.extract.base import ExtractResult
from services.extract.loc_markers import format_pdf_page_marker
from services.extract.ocr_stats import ExtractOcrStats

logger = logging.getLogger(__name__)

# 179: pdf-inspector detect_pdf 会漏报双栏/带图版式（如 WHB 26 号），
# 这里用 PyMuPDF 做补充扫描作为资格判断兜底。阈值内聚在本模块，便于调参。
PDF_INSPECTOR_IMAGE_MIN_PX = 100          # 内容级光栅图的最小像素宽/高（过滤 logo/图标）
PDF_INSPECTOR_MIN_IMAGE_PAGES = 2         # >=2 个页面含内容级图片即回退 mineru
PDF_INSPECTOR_COLUMN_PAGE_FRACTION = 0.5  # 超过半数页面呈多栏版式才判为分栏文档
PDF_INSPECTOR_LOGO_REPEAT_PAGES = 3        # 同一图片出现在 >=3 页视为装饰性 logo


@dataclass(frozen=True)
class PdfInspection:
    classification: str
    confidence: float
    page_count: int
    pages_needing_ocr: tuple[int, ...]
    has_encoding_issues: bool
    is_complex_layout: bool
    pages_with_tables: tuple[int, ...]
    pages_with_columns: tuple[int, ...]
    pages_with_images: tuple[int, ...]
    supplementary_pages_with_columns: tuple[int, ...]


@dataclass(frozen=True)
class PdfInspectorAttempt:
    result: ExtractResult | None
    fallback_reason: str | None


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _native_worker(operation: str, path: str, conn) -> None:
    """Run one native call in a killable child process."""
    try:
        import pdf_inspector

        if operation == "detect":
            raw = pdf_inspector.detect_pdf(path)
            payload = {
                "pdf_type": _value(raw, "pdf_type", _value(raw, "classification", "")),
                "confidence": _value(raw, "confidence", 0.0),
                "page_count": _value(raw, "page_count", 0),
                "pages_needing_ocr": list(_value(raw, "pages_needing_ocr", []) or []),
                "has_encoding_issues": _value(raw, "has_encoding_issues", False),
                "is_complex_layout": _value(raw, "is_complex_layout", False),
                "pages_with_tables": list(_value(raw, "pages_with_tables", []) or []),
                "pages_with_columns": list(_value(raw, "pages_with_columns", []) or []),
            }
        elif operation == "extract_pages":
            raw = pdf_inspector.extract_pages_markdown(path)
            payload = []
            for page in (_value(raw, "pages", raw) or []):
                payload.append(
                    {
                        "page": _value(page, "page", None),
                        "markdown": _value(page, "markdown", _value(page, "text", "")),
                    }
                )
        else:
            raise ValueError(f"unknown pdf-inspector operation: {operation}")
        conn.send({"ok": True, "payload": payload})
    except Exception as exc:
        conn.send(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            }
        )
    finally:
        conn.close()


def _run_native_call(
    operation: str,
    path: str,
    *,
    timeout_sec: float = KB_PDF_INSPECTOR_TIMEOUT_SEC,
    worker=_native_worker,
) -> Any:
    context = multiprocessing.get_context("spawn")
    parent_conn, child_conn = context.Pipe(duplex=False)
    process = context.Process(target=worker, args=(operation, path, child_conn))
    process.daemon = True
    process.start()
    child_conn.close()
    try:
        if not parent_conn.poll(max(0.01, timeout_sec)):
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            raise TimeoutError(f"pdf-inspector {operation} timed out after {timeout_sec}s")
        response = parent_conn.recv()
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        parent_conn.close()
    if not response.get("ok"):
        raise RuntimeError(
            f"pdf-inspector {operation} failed: {response.get('error_type', 'unknown')}"
        )
    return response.get("payload")


def _inspect_pdf(
    path: str,
    *,
    timeout_sec: float = KB_PDF_INSPECTOR_TIMEOUT_SEC,
) -> PdfInspection:
    try:
        raw = _run_native_call("detect", path, timeout_sec=timeout_sec)
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("pdf-inspector is not installed") from exc

    classification = _value(raw, "pdf_type", _value(raw, "classification", ""))
    classification = str(_value(classification, "value", classification)).lower()
    pages_needing_ocr = tuple(int(page) for page in (_value(raw, "pages_needing_ocr", []) or []))
    pages_with_images, supplementary_pages_with_columns = _supplementary_layout_scan(path)
    return PdfInspection(
        classification=classification,
        confidence=float(_value(raw, "confidence", 0.0) or 0.0),
        page_count=int(_value(raw, "page_count", _value(raw, "num_pages", 0)) or 0),
        pages_needing_ocr=pages_needing_ocr,
        has_encoding_issues=bool(_value(raw, "has_encoding_issues", False)),
        is_complex_layout=bool(_value(raw, "is_complex_layout", False)),
        pages_with_tables=tuple(int(page) for page in (_value(raw, "pages_with_tables", []) or [])),
        pages_with_columns=tuple(int(page) for page in (_value(raw, "pages_with_columns", []) or [])),
        pages_with_images=pages_with_images,
        supplementary_pages_with_columns=supplementary_pages_with_columns,
    )


def _extract_pages_markdown(
    path: str,
    *,
    timeout_sec: float = KB_PDF_INSPECTOR_TIMEOUT_SEC,
) -> list[Any]:
    return list(_run_native_call("extract_pages", path, timeout_sec=timeout_sec) or [])


def _pdf_page_count(path: str) -> int | None:
    if not os.path.isfile(path):
        return None
    import fitz

    doc = fitz.open(path)
    try:
        return doc.page_count
    finally:
        doc.close()


def _page_has_columns(page: Any, *, min_blocks: int = 5, min_span_ratio: float = 0.5) -> bool:
    """Detect a true multi-column page from text-block x-position clustering.

    Only counts a cluster as a genuine column when it holds enough body blocks
    (``min_blocks``) that together span a substantial share of the page height
    (``min_span_ratio``). This avoids mistaking narrow tables / indented notes /
    small side elements in otherwise single-column reports for a real 2-column
    layout.
    """
    blocks = page.get_text("blocks")
    body = [b for b in blocks if b[6] == 0 and (b[3] - b[1]) >= 6.0]
    if len(body) < 4:
        return False
    width = page.rect.width
    height = page.rect.height
    if width <= 0 or height <= 0:
        return False
    gap = 0.10 * width
    xs = sorted(b[0] for b in body)
    clusters: list[list[float]] = []
    for x in xs:
        if clusters and x - clusters[-1][-1] <= gap:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    tall_columns = 0
    for cluster in clusters:
        selected = [b for b in body if b[0] in cluster]
        if len(selected) < min_blocks:
            continue
        y0 = min(b[1] for b in selected)
        y1 = max(b[3] for b in selected)
        if (y1 - y0) / height >= min_span_ratio:
            tall_columns += 1
    return tall_columns >= 2


def _page_has_content_image(page: Any, *, min_px: int, logo_xrefs: set[int]) -> bool:
    for image in page.get_images(full=True):
        # get_images(full=True) tuple: [xref, smask, width, height, ...]
        if image[0] in logo_xrefs:
            continue
        try:
            width = int(image[2])
            height = int(image[3])
        except (TypeError, ValueError, IndexError):
            continue
        if width >= min_px and height >= min_px:
            return True
    return False


def _supplementary_layout_scan(
    path: str,
    *,
    min_image_px: int = PDF_INSPECTOR_IMAGE_MIN_PX,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return 1-based page lists (pages_with_images, pages_with_columns).

    pdf-inspector ``detect_pdf`` misses image-heavy and multi-column PDFs, so we
    fall back on a PyMuPDF scan as a supplementary signal before deciding the
    fast path is eligible. Fails open (empty tuples) so the fast path is never
    broken by a scanning error.
    """
    if not os.path.isfile(path):
        return (), ()
    try:
        import fitz
    except ImportError:
        return (), ()
    pages_with_images: list[int] = []
    pages_with_columns: list[int] = []
    try:
        doc = fitz.open(path)
        try:
            page_count = doc.page_count
            xref_pages: dict[int, set[int]] = {}
            for index in range(page_count):
                for image in doc[index].get_images(full=True):
                    xref_pages.setdefault(image[0], set()).add(index)
            logo_xrefs = {
                xref
                for xref, pages in xref_pages.items()
                if len(pages) >= PDF_INSPECTOR_LOGO_REPEAT_PAGES
            }
            for index in range(page_count):
                page = doc[index]
                if _page_has_content_image(page, min_px=min_image_px, logo_xrefs=logo_xrefs):
                    pages_with_images.append(index + 1)
                if _page_has_columns(page):
                    pages_with_columns.append(index + 1)
        finally:
            doc.close()
    except Exception:
        logger.warning("pdf_inspector supplementary layout scan failed path=%s", path, exc_info=True)
        return (), ()
    return tuple(pages_with_images), tuple(pages_with_columns)


def _supplementary_fallback_reason(inspection: PdfInspection) -> str | None:
    pages_with_images = inspection.pages_with_images or ()
    if len(pages_with_images) >= PDF_INSPECTOR_MIN_IMAGE_PAGES:
        return "images_detected"
    if (
        inspection.page_count > 0
        and (inspection.supplementary_pages_with_columns or ())
        and len(inspection.supplementary_pages_with_columns or ()) / inspection.page_count
        >= PDF_INSPECTOR_COLUMN_PAGE_FRACTION
    ):
        return "columns_detected"
    return None


def _page_markdown(page: Any) -> str:
    if isinstance(page, str):
        return page.strip()
    return str(_value(page, "markdown", _value(page, "text", "")) or "").strip()


def _page_number(page: Any) -> int | None:
    value = _value(page, "page", None)
    return int(value) if value is not None else None


def build_pdf_marked_body(pages: list[Any], *, page_count: int) -> str:
    """Build FileX's 1-based page-marker contract, including empty pages."""
    if page_count <= 0 or len(pages) != page_count:
        raise ValueError(f"pdf-inspector page count mismatch: pages={len(pages)} expected={page_count}")

    parts: list[str] = []
    for page_number, page in enumerate(pages, start=1):
        source_page = _page_number(page)
        if source_page is not None and source_page != page_number - 1:
            raise ValueError(
                f"pdf-inspector page order mismatch: source={source_page} expected={page_number - 1}"
            )
        marker = format_pdf_page_marker(page_number).rstrip("\n")
        text = _page_markdown(page)
        parts.append(f"{marker}\n{text}" if text else marker)
    return "\n\n".join(parts).strip()


def _is_eligible(
    inspection: PdfInspection,
    *,
    min_confidence: float,
    max_pages: int,
) -> bool:
    return (
        inspection.classification == "text_based"
        and inspection.confidence >= min_confidence
        and not inspection.pages_needing_ocr
        and not inspection.has_encoding_issues
        and not inspection.is_complex_layout
        and not inspection.pages_with_tables
        and not inspection.pages_with_columns
        and _supplementary_fallback_reason(inspection) is None
        and inspection.page_count > 0
        and inspection.page_count <= max_pages
    )


def _fallback_reason(
    inspection: PdfInspection,
    *,
    min_confidence: float,
    max_pages: int,
) -> str | None:
    if inspection.classification != "text_based":
        return f"classification={inspection.classification or 'unknown'}"
    if inspection.confidence < min_confidence:
        return "low_confidence"
    if inspection.pages_needing_ocr:
        return "pages_needing_ocr"
    if inspection.has_encoding_issues:
        return "encoding_issues"
    if inspection.is_complex_layout:
        return "complex_layout"
    if inspection.pages_with_tables:
        return "tables_detected"
    if inspection.pages_with_columns:
        return "columns_detected"
    supplementary_reason = _supplementary_fallback_reason(inspection)
    if supplementary_reason:
        return supplementary_reason
    if inspection.page_count <= 0:
        return "invalid_page_count"
    if inspection.page_count > max_pages:
        return "page_limit"
    return None


def inspect_pdf_with_fallback(
    path: str,
    *,
    file_id: int | None = None,
    mode: str,
    min_confidence: float = KB_PDF_INSPECTOR_MIN_CONFIDENCE,
    max_pages: int = KB_EXTRACT_MAX_PAGES,
    timeout_sec: float = KB_PDF_INSPECTOR_TIMEOUT_SEC,
) -> PdfInspectorAttempt:
    """Run the inspector and preserve a bounded reason when legacy must run."""
    if mode == "off":
        return PdfInspectorAttempt(None, None)

    try:
        inspection = _inspect_pdf(path, timeout_sec=timeout_sec)
        logger.info(
            "pdf_inspector preflight file_id=%s classification=%s confidence=%.4f pages=%s ocr_pages=%s encoding_issues=%s image_pages=%s column_pages=%s",
            file_id,
            inspection.classification,
            inspection.confidence,
            inspection.page_count,
            list(inspection.pages_needing_ocr or ()),
            inspection.has_encoding_issues,
            list(inspection.pages_with_images or ()),
            list(inspection.supplementary_pages_with_columns or ()),
        )
        reason = _fallback_reason(
            inspection,
            min_confidence=min_confidence,
            max_pages=max_pages,
        )
        if mode == "detect-only":
            logger.info(
                "pdf_inspector detect_only file_id=%s eligible=%s reason=%s",
                file_id,
                _is_eligible(
                    inspection,
                    min_confidence=min_confidence,
                    max_pages=max_pages,
                ),
                reason,
            )
            return PdfInspectorAttempt(None, None)
        actual_page_count = _pdf_page_count(path)
        if actual_page_count is not None and actual_page_count != inspection.page_count:
            return PdfInspectorAttempt(None, "page_count_mismatch")
        if actual_page_count is not None and actual_page_count > max_pages:
            return PdfInspectorAttempt(None, "page_limit")
        if not _is_eligible(
            inspection,
            min_confidence=min_confidence,
            max_pages=max_pages,
        ):
            return PdfInspectorAttempt(None, reason or "ineligible")
        pages = _extract_pages_markdown(path, timeout_sec=timeout_sec)
        body = build_pdf_marked_body(pages, page_count=inspection.page_count)
        if not body:
            raise ValueError("pdf-inspector returned empty markdown")
        return PdfInspectorAttempt(
            ExtractResult(
                text=body,
                engine="pdf-inspector",
                ocr_stats=ExtractOcrStats(
                    ocr_used=False,
                    ocr_engine="none",
                    pdf_class="text_layer",
                    text_layer_page_count=inspection.page_count,
                ),
            ),
            None,
        )
    except Exception as exc:
        logger.warning("pdf_inspector fallback file_id=%s reason=%s", file_id, exc)
        return PdfInspectorAttempt(None, f"error={type(exc).__name__}")


def try_extract_pdf_with_inspector(
    path: str,
    *,
    file_id: int | None = None,
    mode: str,
    min_confidence: float = KB_PDF_INSPECTOR_MIN_CONFIDENCE,
    max_pages: int = KB_EXTRACT_MAX_PAGES,
    timeout_sec: float = KB_PDF_INSPECTOR_TIMEOUT_SEC,
) -> ExtractResult | None:
    """Return a fast-path result, or None so the caller can use the legacy path."""
    return inspect_pdf_with_fallback(
        path,
        file_id=file_id,
        mode=mode,
        min_confidence=min_confidence,
        max_pages=max_pages,
        timeout_sec=timeout_sec,
    ).result


def try_pdf_inspector_fast_path(f, *, db=None) -> ExtractResult | None:
    """Return pdf-inspector fast-path result for an eligible PDF, else None.

    Called from provider routing so the fast path engages even when the
    configured/route extract provider is a sidecar (mineru/docling) instead of
    legacy. Eligibility and fallback semantics are owned by
    ``inspect_pdf_with_fallback``; this helper only resolves the on-disk path
    and gates on the pdf-inspector runtime switch.
    """
    from config import KB_PDF_INSPECTOR_MODE
    from services.pdf_inspector_switch_service import get_pdf_inspector_enabled

    if not get_pdf_inspector_enabled(db):
        return None

    from services.extract.policy import get_extension_from_file

    if get_extension_from_file(f) != "pdf":
        return None

    from services.md_paths import resolve_upload_path

    path = resolve_upload_path(f.file_path) or f.file_path
    if not path or not os.path.isfile(path):
        return None

    return try_extract_pdf_with_inspector(
        path,
        file_id=f.id,
        mode=KB_PDF_INSPECTOR_MODE,
    )
