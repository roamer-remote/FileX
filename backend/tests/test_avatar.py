# Copyright (c) 2026 徐泽宇
"""Tests for user avatar stored in DB (POST/GET/DELETE /api/auth/avatar).

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from io import BytesIO

from fastapi import status
from PIL import Image


def _mini_png_bytes() -> bytes:
    im = Image.new("RGB", (4, 4), color=(20, 120, 200))
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_avatar_upload_get_delete_roundtrip(client, jwt_token):
    png = _mini_png_bytes()
    up = client.post(
        "/api/auth/avatar",
        headers={"Authorization": f"Bearer {jwt_token}"},
        files={"file": ("a.png", png, "image/png")},
    )
    assert up.status_code == 200
    assert up.json().get("has_avatar") is True

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {jwt_token}"})
    assert me.status_code == 200
    assert me.json().get("has_avatar") is True

    av = client.get("/api/auth/avatar", headers={"Authorization": f"Bearer {jwt_token}"})
    assert av.status_code == 200
    assert av.headers.get("content-type", "").startswith("image/")
    assert av.content == png

    dl = client.delete("/api/auth/avatar", headers={"Authorization": f"Bearer {jwt_token}"})
    assert dl.status_code == 200
    assert dl.json().get("has_avatar") is False

    g404 = client.get("/api/auth/avatar", headers={"Authorization": f"Bearer {jwt_token}"})
    assert g404.status_code == status.HTTP_404_NOT_FOUND


def test_avatar_get_404_when_missing(client, jwt_token):
    r = client.get("/api/auth/avatar", headers={"Authorization": f"Bearer {jwt_token}"})
    assert r.status_code == status.HTTP_404_NOT_FOUND


def test_avatar_rejects_oversize(client, jwt_token):
    big = b"\xff" * (2 * 1024 * 1024 + 1)
    r = client.post(
        "/api/auth/avatar",
        headers={"Authorization": f"Bearer {jwt_token}"},
        files={"file": ("x.bin", big, "application/octet-stream")},
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST
