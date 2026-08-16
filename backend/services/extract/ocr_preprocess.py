# Copyright (c) 2026 徐泽宇
"""Optional OCR preprocessing for legacy RapidOCR/Paddle paths (103 P1)."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from config import (
    KB_OCR_PREPROCESS_CONTRAST,
    KB_OCR_PREPROCESS_DESKEW,
    KB_OCR_PREPROCESS_ENABLED,
    KB_OCR_PREPROCESS_ROTATE,
)

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger(__name__)


def preprocess_pil_image(img: Image.Image) -> Image.Image:
    """Apply enabled preprocess steps; no-op when master switch is off."""
    if not KB_OCR_PREPROCESS_ENABLED:
        return img
    out = img.convert("RGB")
    if KB_OCR_PREPROCESS_ROTATE:
        out = _auto_rotate(out)
    if KB_OCR_PREPROCESS_DESKEW:
        out = _deskew(out)
    if KB_OCR_PREPROCESS_CONTRAST:
        out = _enhance_contrast(out)
    return out


def maybe_preprocess_image_bytes(image_bytes: bytes) -> bytes:
    if not KB_OCR_PREPROCESS_ENABLED or not image_bytes:
        return image_bytes
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as img:
        processed = preprocess_pil_image(img)
        buf = io.BytesIO()
        processed.save(buf, format="PNG")
        return buf.getvalue()


def _auto_rotate(img: Image.Image) -> Image.Image:
    from PIL import ImageOps

    try:
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            img = transposed
    except Exception:
        logger.debug("EXIF transpose skipped", exc_info=True)

    try:
        import cv2
        import numpy as np
    except ImportError:
        return img

    best = img
    best_score = _rotation_score(np.array(img.convert("L")))
    for angle in (90, 180, 270):
        rotated = img.rotate(angle, expand=True)
        score = _rotation_score(np.array(rotated.convert("L")))
        if score > best_score:
            best_score = score
            best = rotated
    return best


def _rotation_score(gray: object) -> float:
    import numpy as np

    arr = np.asarray(gray)
    if arr.size == 0:
        return 0.0
    row_sums = arr.sum(axis=1)
    return float(row_sums.std())


def _deskew(img: Image.Image) -> Image.Image:
    try:
        import cv2
        import numpy as np
    except ImportError:
        logger.debug("deskew skipped: cv2 unavailable")
        return img

    arr = np.array(img)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return img
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) < 0.5:
        return img
    h, w = arr.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(
        arr,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    from PIL import Image

    return Image.fromarray(rotated)


def _enhance_contrast(img: Image.Image) -> Image.Image:
    try:
        import cv2
        import numpy as np
    except ImportError:
        from PIL import ImageEnhance

        return ImageEnhance.Contrast(img).enhance(1.25)

    arr = np.array(img)
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    merged = cv2.merge((l_channel, a_channel, b_channel))
    enhanced = cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)
    from PIL import Image

    return Image.fromarray(enhanced)
