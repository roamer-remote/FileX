# Copyright (c) 2026 徐泽宇
"""LiteParse OCR HTTP bridge contract tests.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from services.extract.liteparse_ocr_bridge import app
from services.extract.ocr import _polygon_to_bbox, ocr_image_bytes_for_liteparse


def test_polygon_to_bbox_from_quad():
    poly = [[10, 20], [60, 20], [60, 40], [10, 40]]
    assert _polygon_to_bbox(poly) == [10.0, 20.0, 60.0, 40.0]


def test_ocr_image_bytes_for_liteparse_empty():
    assert ocr_image_bytes_for_liteparse(b"") == []


def test_ocr_bridge_endpoint_schema(monkeypatch):
    def fake_ocr(image_bytes: bytes, *, language: str | None = None):
        return [
            {
                "text": "hello",
                "bbox": [0.0, 0.0, 100.0, 50.0],
                "confidence": 0.9,
            },
        ]

    monkeypatch.setattr(
        "services.extract.liteparse_ocr_bridge.ocr_image_bytes_for_liteparse",
        fake_ocr,
    )
    img = Image.new("RGB", (100, 50), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    client = TestClient(app)
    resp = client.post(
        "/ocr",
        files={"file": ("page.png", buf.getvalue(), "image/png")},
        data={"language": "zh"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert len(body["results"]) == 1
    row = body["results"][0]
    assert row["text"] == "hello"
    assert len(row["bbox"]) == 4
    assert 0.0 <= row["confidence"] <= 1.0


def test_ocr_bridge_empty_file():
    client = TestClient(app)
    resp = client.post("/ocr", files={"file": ("empty.png", b"", "image/png")})
    assert resp.status_code == 400
