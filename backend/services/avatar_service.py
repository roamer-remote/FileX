# Copyright (c) 2026 徐泽宇
"""Validate user avatar uploads (stored in DB as bytes + MIME).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

MAX_AVATAR_BYTES = 2 * 1024 * 1024

_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


def validate_avatar_image(raw: bytes) -> tuple[str, bytes]:
    """Return (mime, bytes) for storage. Raises ValueError with Chinese detail for API."""
    if len(raw) > MAX_AVATAR_BYTES:
        raise ValueError("头像文件不能超过 2MB")
    if len(raw) < 16:
        raise ValueError("无效的图片文件")

    try:
        probe = Image.open(BytesIO(raw))
        probe.verify()
    except Exception:
        raise ValueError("无法识别为有效图片，请使用 JPG、PNG、WebP 或 GIF")

    im = Image.open(BytesIO(raw))
    fmt = im.format
    if fmt not in _FORMAT_TO_MIME:
        raise ValueError("仅支持 JPG、PNG、WebP、GIF 格式的图片")

    return _FORMAT_TO_MIME[fmt], raw
