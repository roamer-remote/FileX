# Copyright (c) 2026 徐泽宇
"""025: extract location markers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.extract.loc_markers import (
    format_pdf_page_marker,
    format_sheet_marker,
    format_slide_marker,
    parse_loc_marker_line,
    split_body_by_loc_markers,
)
from services.extract.pptx import build_pptx_marked_body
from services.extract.xlsx import build_xlsx_marked_body
from services.kb_citation import build_citation_label


def test_format_markers():
    assert "page=2" in format_pdf_page_marker(2)
    assert "slide=3" in format_slide_marker(3)
    assert "sheet_index=1" in format_sheet_marker(1, "汇总")
    assert 'sheet_name="汇总"' in format_sheet_marker(1, "汇总")


def test_parse_loc_marker_line():
    loc = parse_loc_marker_line("<!-- filex:loc type=pdf_page page=5 -->")
    assert loc is not None
    assert loc.loc_type == "pdf_page"
    assert loc.loc_start == 5


def test_split_body_by_loc_markers():
    body = format_pdf_page_marker(1) + "alpha\n\n" + format_pdf_page_marker(2) + "beta"
    parts = split_body_by_loc_markers(body)
    assert len(parts) == 2
    assert parts[0][0] is not None and parts[0][0].loc_start == 1
    assert "alpha" in parts[0][1]
    assert parts[1][0] is not None and parts[1][0].loc_start == 2


def test_build_citation_label_pdf():
    tier, label, loc = build_citation_label(
        "合同.pdf", loc_type="pdf_page", loc_start=12, loc_end=12,
    )
    assert tier == "paginated"
    assert label == "《合同.pdf》第 12 页"
    assert loc == {"type": "pdf_page", "page": 12}


def test_build_citation_label_sheet():
    tier, label, loc = build_citation_label(
        "报表.xlsx", loc_type="sheet", loc_start=2, loc_end=2, loc_label="汇总",
    )
    assert tier == "paginated"
    assert "第 2 个工作表" in label
    assert "汇总" in label
    assert loc["sheet_index"] == 2


def test_build_citation_label_document_only():
    tier, label, loc = build_citation_label("说明.docx")
    assert tier == "document_only"
    assert label == "《说明.docx》"
    assert loc is None


@patch("services.extract.pptx.Presentation")
def test_build_pptx_marked_body(mock_prs_cls):
    slide_with_text = MagicMock()
    shape = MagicMock()
    shape.text = "标题"
    slide_with_text.shapes = [shape]
    slide_empty = MagicMock()
    slide_empty.shapes = []
    mock_prs_cls.return_value.slides = [slide_with_text, slide_empty, slide_with_text]
    body = build_pptx_marked_body("/tmp/a.pptx")
    assert "slide=1" in body
    assert "slide=2" in body
    assert "slide=3" in body
    assert body.index("slide=2") < body.index("slide=3")


@patch("services.extract.xlsx.load_workbook")
def test_build_xlsx_marked_body(mock_load):
    sheet = MagicMock()
    sheet.title = "SheetA"
    sheet.iter_rows.return_value = [[MagicMock(value="x")]]
    wb = MagicMock()
    wb.worksheets = [sheet]
    mock_load.return_value = wb
    body = build_xlsx_marked_body("/tmp/a.xlsx")
    assert "sheet_index=1" in body
    assert "SheetA" in body
