# Copyright (c) 2026 徐泽宇
"""MarkItDown integration in legacy extract path.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from models.file import File as FileModel
from services.extract.base import ExtractResult
from services.extract.markitdown_extract import try_markitdown
from services.extract.pdf import MIN_TEXT_CHARS_PER_PAGE, _pages_are_text_layer
from services.extract.router import extract_text_from_file


def test_markitdown_eligible_extensions():
    from services.extract.policy import MARKITDOWN_ELIGIBLE_EXTENSIONS

    assert MARKITDOWN_ELIGIBLE_EXTENSIONS == frozenset({"pdf", "docx", "pptx", "xlsx"})
    assert "xls" not in MARKITDOWN_ELIGIBLE_EXTENSIONS


def test_try_markitdown_disabled(tmp_path):
    p = tmp_path / "a.docx"
    p.write_bytes(b"x")
    with patch("services.extract.markitdown_extract.KB_MARKITDOWN_ENABLED", False):
        assert try_markitdown(str(p), "docx", file_id=1) is None


def test_try_markitdown_success(tmp_path):
    p = tmp_path / "a.docx"
    p.write_bytes(b"x")
    fake_result = MagicMock(text_content="# hello", markdown="# hello")
    with patch("services.extract.markitdown_extract.KB_MARKITDOWN_ENABLED", True):
        with patch("services.extract.markitdown_extract.MarkItDown") as MockMd:
            MockMd.return_value.convert_local.return_value = fake_result
            out = try_markitdown(str(p), "docx", file_id=42)
    assert out is not None
    assert out.text == "# hello"
    assert out.engine == "markitdown"


def test_try_markitdown_empty_falls_back(tmp_path):
    p = tmp_path / "a.docx"
    p.write_bytes(b"x")
    fake_result = MagicMock(text_content="", markdown="")
    with patch("services.extract.markitdown_extract.KB_MARKITDOWN_ENABLED", True):
        with patch("services.extract.markitdown_extract.MarkItDown") as MockMd:
            MockMd.return_value.convert_local.return_value = fake_result
            assert try_markitdown(str(p), "docx", file_id=1) is None


def _file(**kwargs) -> FileModel:
    defaults = dict(
        id=1,
        filename="f",
        original_name="f.docx",
        file_path="/tmp/f.docx",
        file_size=10,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        user_id=1,
    )
    defaults.update(kwargs)
    return FileModel(**defaults)


def test_router_docx_uses_markitdown(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_MARKITDOWN_ENABLED", "1")
    p = tmp_path / "a.docx"
    p.write_bytes(b"fake")
    f = _file(file_path=str(p), original_name="a.docx")
    with patch("services.extract.markitdown_extract.try_markitdown") as mock_md:
        mock_md.return_value = ExtractResult(text="md out", engine="markitdown")
        result = extract_text_from_file(f)
    mock_md.assert_called_once_with(str(p), "docx", file_id=1)
    assert result.engine == "markitdown"
    assert result.text == "md out"


def test_router_docx_falls_back_to_legacy(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_MARKITDOWN_ENABLED", "1")
    p = tmp_path / "a.docx"
    p.write_bytes(b"fake")
    f = _file(file_path=str(p), original_name="a.docx")
    with patch("services.extract.markitdown_extract.try_markitdown", return_value=None):
        with patch("services.extract.router.extract_docx") as mock_legacy:
            mock_legacy.return_value = ExtractResult(text="legacy", engine="python-docx")
            result = extract_text_from_file(f)
    assert result.engine == "python-docx"


def test_router_xls_normalized_uses_markitdown_on_xlsx(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_MARKITDOWN_ENABLED", "1")
    orig = tmp_path / "a.xls"
    orig.write_bytes(b"fake xls")
    norm = tmp_path / "a.xlsx"
    norm.write_bytes(b"fake xlsx")
    f = _file(
        file_path=str(orig),
        original_name="a.xls",
        normalized_path=str(norm),
        mime_type="application/vnd.ms-excel",
    )
    with patch("services.extract.markitdown_extract.try_markitdown") as mock_md:
        mock_md.return_value = ExtractResult(text="sheet md", engine="markitdown")
        result = extract_text_from_file(f)
    mock_md.assert_called_once_with(str(norm), "xlsx", file_id=1)
    assert result.engine == "libreoffice+markitdown"


def test_router_doc_normalized_falls_back_markitdown(monkeypatch, tmp_path):
    """LO 归一化 .doc → .docx 后 MarkItDown 失败，回退 legacy 仍须 libreoffice+ 前缀。"""
    monkeypatch.setenv("KB_MARKITDOWN_ENABLED", "1")
    orig = tmp_path / "a.doc"
    orig.write_bytes(b"fake doc")
    norm = tmp_path / "a.docx"
    norm.write_bytes(b"fake docx")
    f = _file(
        file_path=str(orig),
        original_name="a.doc",
        normalized_path=str(norm),
        mime_type="application/msword",
    )
    with patch("services.extract.markitdown_extract.try_markitdown", return_value=None):
        with patch("services.extract.router.extract_docx") as mock_legacy:
            mock_legacy.return_value = ExtractResult(text="legacy doc", engine="python-docx")
            result = extract_text_from_file(f)
    mock_legacy.assert_called_once_with(str(norm))
    assert result.engine == "libreoffice+python-docx"
    assert result.text == "legacy doc"


def test_router_image_unchanged(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_MARKITDOWN_ENABLED", "1")
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    f = _file(
        file_path=str(p),
        original_name="a.png",
        mime_type="image/png",
    )
    with patch("services.extract.markitdown_extract.try_markitdown") as mock_md:
        with patch("services.extract.router.extract_image") as mock_img:
            mock_img.return_value = ExtractResult(text="ocr text", engine="rapidocr")
            result = extract_text_from_file(f)
    mock_md.assert_not_called()
    assert result.engine == "rapidocr"


def test_pdf_text_layer_tries_markitdown(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_MARKITDOWN_ENABLED", "1")
    import fitz

    p = tmp_path / "text.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "x" * MIN_TEXT_CHARS_PER_PAGE)
    doc.save(str(p))
    doc.close()
    with patch("services.extract.markitdown_extract.try_markitdown") as mock_md:
        mock_md.return_value = ExtractResult(text="# pdf md", engine="markitdown")
        from services.extract.pdf import extract_pdf

        result = extract_pdf(str(p), file_id=99)
    mock_md.assert_called_once()
    assert result.engine == "markitdown+pymupdf-loc"


def test_pdf_mixed_skips_markitdown(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_MARKITDOWN_ENABLED", "1")
    import fitz

    p = tmp_path / "scan.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "short")
    doc.save(str(p))
    doc.close()
    with patch("services.extract.markitdown_extract.try_markitdown") as mock_md:
        with patch("services.extract.pdf.ocr_pil_image_with_confidence", return_value=("ocr page", None)):
            from services.extract.pdf import extract_pdf

            result = extract_pdf(str(p), file_id=99)
    mock_md.assert_not_called()
    assert "rapidocr" in result.engine or result.text


def test_pages_are_text_layer():
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "a" * MIN_TEXT_CHARS_PER_PAGE)
    assert _pages_are_text_layer(doc, 1) is True
    doc.close()

    doc2 = fitz.open()
    page2 = doc2.new_page()
    page2.insert_text((72, 72), "tiny")
    assert _pages_are_text_layer(doc2, 1) is False
    doc2.close()
