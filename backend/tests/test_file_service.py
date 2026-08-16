# Copyright (c) 2026 徐泽宇
"""file_service：扩展名白名单与 MIME 映射。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""
import os
from io import BytesIO

import pytest
from fastapi import UploadFile

from services.file_service import (
    get_mime_type,
    should_generate_thumbnail,
    thumb_jpeg_path,
    validate_file,
)


def test_validate_file_accepts_html_and_htm():
    for name in ("page.html", "legacy.htm"):
        uf = UploadFile(filename=name, file=BytesIO(b"<html><body>x</body></html>"))
        validate_file(uf)


def test_get_mime_type_html():
    assert get_mime_type("a.html") == "text/html"
    assert get_mime_type("b.htm") == "text/html"


def test_validate_file_rejects_unknown_ext():
    uf = UploadFile(filename="x.exe", file=BytesIO(b"MZ"))
    with pytest.raises(ValueError, match="不支持的资料类型"):
        validate_file(uf)


def test_should_generate_thumbnail_skips_office():
    assert should_generate_thumbnail("/tmp/u_foo.pdf") is True
    assert should_generate_thumbnail("/tmp/u_foo.xlsx") is False
    assert should_generate_thumbnail("/tmp/u_foo.docx") is False


def test_thumb_jpeg_path_stem():
    p = thumb_jpeg_path("/data/1/2025-01/ab12_file.png")
    assert p.endswith(os.path.join(".thumbnails", "ab12_file.jpg"))
