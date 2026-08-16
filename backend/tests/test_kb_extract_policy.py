# Copyright (c) 2026 徐泽宇
"""KB extract policy: needs_extract by extension and existing MD.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from models.file import File as FileModel
from services.extract.policy import needs_extract, get_extension_from_file, EXTRACT_EXTENSIONS, supports_reextract, is_markdown_source_file
from services.file_service import get_extension


def test_extract_extensions_include_office_and_pdf():
    assert "pdf" in EXTRACT_EXTENSIONS
    assert "docx" in EXTRACT_EXTENSIONS
    assert "doc" in EXTRACT_EXTENSIONS
    assert "jpg" in EXTRACT_EXTENSIONS


def test_needs_extract_pdf_without_md():
    f = FileModel(
        id=1,
        filename="a.pdf",
        original_name="scan.pdf",
        file_path="/tmp/x.pdf",
        file_size=100,
        mime_type="application/pdf",
        user_id=1,
        has_md=False,
    )
    assert needs_extract(f) is True


def test_needs_extract_false_when_md_has_content(tmp_path):
    md = tmp_path / "n.md"
    md.write_text("# note\nhello", encoding="utf-8")
    f = FileModel(
        id=2,
        filename="a.pdf",
        original_name="scan.pdf",
        file_path="/tmp/x.pdf",
        file_size=100,
        mime_type="application/pdf",
        user_id=1,
        has_md=True,
        md_file_path=str(md),
    )
    assert needs_extract(f) is False


def test_md_supports_reextract_not_auto_extract(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("hello", encoding="utf-8")
    f = FileModel(
        id=3,
        filename="a",
        original_name="a.md",
        file_path=str(src),
        file_size=5,
        mime_type="text/markdown",
        user_id=1,
        has_md=False,
    )
    assert is_markdown_source_file(f) is True
    assert needs_extract(f) is False
    assert supports_reextract(f) is True


def test_txt_supports_reextract_not_auto_extract(tmp_path):
    src = tmp_path / "notes.txt"
    src.write_text("hello txt", encoding="utf-8")
    f = FileModel(
        id=4,
        filename="notes",
        original_name="notes.txt",
        file_path=str(src),
        file_size=9,
        mime_type="text/plain",
        user_id=1,
        has_md=False,
    )
    assert is_markdown_source_file(f) is True
    assert needs_extract(f) is False
    assert supports_reextract(f) is True
