# Copyright (c) 2026 徐泽宇
"""file_service 业务逻辑模块。

Authors:
    徐泽宇
"""

import os
import re
import uuid
import hashlib
from datetime import datetime
from html.parser import HTMLParser

from fastapi import UploadFile

from config import UPLOAD_DIR, ALLOWED_EXTENSIONS
from models.file import File

TEXT_THUMB_READ_BYTES = 65536
TEXT_THUMB_MAX_LINES = 52
TEXT_THUMB_LINE_CHARS = 100
CANVAS_W, CANVAS_H = 380, 380

OFFICE_EXTENSIONS = frozenset({"doc", "docx", "ppt", "pptx", "xls", "xlsx"})
THUMBNAIL_SOURCE_EXTENSIONS = frozenset(
    {"pdf", "jpg", "jpeg", "png", "gif", "bmp", "webp", "txt", "md", "html", "htm"}
)

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
)


def get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def sanitize_upload_basename(filename: str) -> str:
    """去掉路径分量，仅保留 basename（防御纵深，UUID 前缀已防穿越）。"""
    name = os.path.basename((filename or "").replace("\\", "/")).strip()
    if not name or name in (".", ".."):
        return "unknown"
    return name


def get_mime_type(filename: str) -> str:
    ext = get_extension(filename)
    mime_map = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "webp": "image/webp",
        "txt": "text/plain",
        "md": "text/markdown",
        "markdown": "text/markdown",
        "html": "text/html",
        "htm": "text/html",
        "eml": "message/rfc822",
    }
    return mime_map.get(ext, "application/octet-stream")


def validate_file(upload_file: UploadFile):
    ext = get_extension(upload_file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"不支持的资料类型: .{ext}")


def save_upload(upload_file: UploadFile, user_id: int, content: bytes | None = None) -> File:
    raw_name = upload_file.filename or "unknown"
    safe_name = sanitize_upload_basename(raw_name)
    ext = get_extension(safe_name)
    now = datetime.now()
    date_dir = now.strftime("%Y-%m")
    user_dir = os.path.join(UPLOAD_DIR, str(user_id), date_dir)
    os.makedirs(user_dir, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    file_path = os.path.join(user_dir, stored_name)

    if content is None:
        content = upload_file.file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    file_size = len(content)

    return File(
        filename=stored_name,
        original_name=safe_name,
        file_path=file_path,
        file_size=file_size,
        mime_type=get_mime_type(safe_name) or upload_file.content_type or "application/octet-stream",
        source_sha256=hashlib.sha256(content).hexdigest(),
        user_id=user_id,
    )


def thumb_jpeg_path(file_path: str) -> str:
    stem = os.path.splitext(os.path.basename(file_path))[0]
    thumb_dir = os.path.join(os.path.dirname(file_path), ".thumbnails")
    return os.path.join(thumb_dir, f"{stem}.jpg")


def legacy_thumb_same_basename_path(file_path: str) -> str:
    thumb_dir = os.path.join(os.path.dirname(file_path), ".thumbnails")
    return os.path.join(thumb_dir, os.path.basename(file_path))


def existing_thumbnail_path(file_path: str) -> str | None:
    jp = thumb_jpeg_path(file_path)
    if os.path.isfile(jp):
        return jp
    leg = legacy_thumb_same_basename_path(file_path)
    if os.path.isfile(leg):
        return leg
    return None


def thumbnail_media_type(thumb_path: str) -> str:
    ext = get_extension(os.path.basename(thumb_path))
    if ext in ("jpg", "jpeg"):
        return "image/jpeg"
    if ext == "png":
        return "image/png"
    if ext == "gif":
        return "image/gif"
    if ext == "webp":
        return "image/webp"
    return "application/octet-stream"


def should_generate_thumbnail(file_path: str) -> bool:
    ext = get_extension(os.path.basename(file_path))
    return ext in THUMBNAIL_SOURCE_EXTENSIONS


def _save_jpeg_thumb(img, out_path: str) -> str | None:
    try:
        from PIL import Image
        from config import THUMBNAIL_SIZE

        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img = img.copy()
        img.thumbnail(THUMBNAIL_SIZE)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        img.save(out_path, "JPEG", quality=88, optimize=True)
        return out_path
    except Exception:
        return None


def _thumb_from_image_file(file_path: str) -> str | None:
    try:
        from PIL import Image

        img = Image.open(file_path)
        return _save_jpeg_thumb(img, thumb_jpeg_path(file_path))
    except Exception:
        return None


def _thumb_from_pdf(file_path: str) -> str | None:
    try:
        import fitz  # PyMuPDF
        from PIL import Image

        doc = fitz.open(file_path)
        if doc.page_count < 1:
            doc.close()
            return None
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        doc.close()
        return _save_jpeg_thumb(img, thumb_jpeg_path(file_path))
    except Exception:
        return None


class _HTMLToText(HTMLParser):
    """_htmlto文本 业务服务。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-12
    """
    def __init__(self):
        super().__init__()
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style") and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip == 0 and data:
            self._chunks.append(data)

    def text(self) -> str:
        return " ".join(self._chunks)


def _html_to_plain(html: str) -> str:
    p = _HTMLToText()
    try:
        p.feed(html)
        p.close()
        s = p.text()
    except Exception:
        s = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
        s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
        s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _read_text_sample(file_path: str, ext: str) -> str:
    try:
        with open(file_path, "rb") as fh:
            raw = fh.read(TEXT_THUMB_READ_BYTES)
        text = raw.decode("utf-8", errors="replace")
    except OSError:
        return ""
    if ext in ("html", "htm"):
        text = _html_to_plain(text)
    return text


def _thumb_from_plain_text(file_path: str, ext: str) -> str | None:
    try:
        from PIL import Image, ImageDraw, ImageFont

        body = _read_text_sample(file_path, ext)
        if not body.strip():
            body = " "

        font = None
        for fp in _FONT_CANDIDATES:
            if os.path.isfile(fp):
                font = ImageFont.truetype(fp, 15)
                break
        if font is None:
            font = ImageFont.load_default()

        img = Image.new("RGB", (CANVAS_W, CANVAS_H), (248, 248, 250))
        draw = ImageDraw.Draw(img)
        y = 10
        x0 = 12
        line_height = 18
        lines_emitted = 0
        for raw_line in body.splitlines():
            if lines_emitted >= TEXT_THUMB_MAX_LINES or y > CANVAS_H - 24:
                break
            line = raw_line.strip() or " "
            while line and lines_emitted < TEXT_THUMB_MAX_LINES and y <= CANVAS_H - 24:
                chunk = line[:TEXT_THUMB_LINE_CHARS]
                line = line[TEXT_THUMB_LINE_CHARS:]
                draw.text((x0, y), chunk, fill=(34, 34, 38), font=font)
                y += line_height
                lines_emitted += 1

        return _save_jpeg_thumb(img, thumb_jpeg_path(file_path))
    except Exception:
        return None


def generate_home_thumbnail(file_path: str) -> str | None:
    if not file_path or not os.path.isfile(file_path):
        return None
    if not should_generate_thumbnail(file_path):
        return None

    ext = get_extension(os.path.basename(file_path))
    if ext in OFFICE_EXTENSIONS:
        return None

    if ext == "pdf":
        return _thumb_from_pdf(file_path)
    if ext in ("jpg", "jpeg", "png", "gif", "bmp", "webp"):
        return _thumb_from_image_file(file_path)
    if ext in ("txt", "md", "html", "htm"):
        return _thumb_from_plain_text(file_path, ext)
    return None


def save_thumbnail(file_path: str):
    """生成首页缩略图（PDF/图片/文本类）；Office 跳过。"""
    return generate_home_thumbnail(file_path)
