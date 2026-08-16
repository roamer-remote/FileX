# Copyright (c) 2026 徐泽宇
"""Tests for extract-asset signed URLs (105)."""

from __future__ import annotations

import os
import time

import pytest
from fastapi.routing import APIRoute

from config import EXTRACT_ASSET_SIGN_MAX_KEYS
from main import app
from models.file import File as FileModel
from services.extract.content_list_persist import extract_assets_dir_for_file
from services.extract_asset_signing import (
    build_signed_extract_asset_token,
    remember_extract_assets_dir,
    verify_signed_extract_asset_token,
)
from tests.conftest import _create_user, make_jwt


def _route_depends(route_path: str, method: str = "GET") -> set[str]:
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path != route_path or method not in route.methods:
            continue
        names: set[str] = set()
        for dep in route.dependant.dependencies:
            if dep.call is not None and hasattr(dep.call, "__name__"):
                names.add(dep.call.__name__)
        return names
    return set()


def _create_file_with_asset(db_session, user, tmp_path, *, filename="doc.pdf") -> tuple[FileModel, str]:
    parent = tmp_path / "owner"
    parent.mkdir(parents=True, exist_ok=True)
    f = FileModel(
        filename=filename,
        original_name=filename,
        file_path=str(parent / filename),
        file_size=1,
        mime_type="application/pdf",
        user_id=user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    assets = extract_assets_dir_for_file(f)
    os.makedirs(assets, exist_ok=True)
    asset_name = "fig1.jpg"
    asset_path = os.path.join(assets, asset_name)
    with open(asset_path, "wb") as fh:
        fh.write(b"img-bytes")
    remember_extract_assets_dir(f.id, assets)
    return f, asset_name


def test_signed_get_route_has_no_get_db_dependency():
    deps = _route_depends("/api/files/signed-extract-assets/{signed_token}", "GET")
    assert "get_db" not in deps


def test_sign_and_download_signed_extract_asset(client, db_session, regular_user, tmp_path):
    token = make_jwt(regular_user.id, regular_user.password_rev)
    f, asset_name = _create_file_with_asset(db_session, regular_user, tmp_path)

    sign_resp = client.post(
        f"/api/files/{f.id}/extract-assets/sign",
        json={"asset_keys": [asset_name]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sign_resp.status_code == 200
    body = sign_resp.json()
    assert body["expires_at"] > int(time.time())
    assert len(body["items"]) == 1
    signed_url = body["items"][0]["url"]
    assert signed_url.startswith("/api/files/signed-extract-assets/")

    get_resp = client.get(signed_url)
    assert get_resp.status_code == 200
    assert get_resp.content == b"img-bytes"


def test_sign_rejects_empty_keys(client, db_session, regular_user, tmp_path):
    token = make_jwt(regular_user.id, regular_user.password_rev)
    f, _ = _create_file_with_asset(db_session, regular_user, tmp_path)

    resp = client.post(
        f"/api/files/{f.id}/extract-assets/sign",
        json={"asset_keys": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_sign_rejects_over_max_keys(client, db_session, regular_user, tmp_path):
    token = make_jwt(regular_user.id, regular_user.password_rev)
    f, _ = _create_file_with_asset(db_session, regular_user, tmp_path)
    keys = [f"k{i}.jpg" for i in range(EXTRACT_ASSET_SIGN_MAX_KEYS + 1)]

    resp = client.post(
        f"/api/files/{f.id}/extract-assets/sign",
        json={"asset_keys": keys},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_sign_forbidden_for_other_user(client, db_session, regular_user, tmp_path):
    other = _create_user(db_session, "other-sign-user")
    other_token = make_jwt(other.id, other.password_rev)
    f, asset_name = _create_file_with_asset(db_session, regular_user, tmp_path)

    resp = client.post(
        f"/api/files/{f.id}/extract-assets/sign",
        json={"asset_keys": [asset_name]},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


def test_signed_get_rejects_invalid_token(client):
    resp = client.get("/api/files/signed-extract-assets/not-a-valid-token")
    assert resp.status_code == 401


def test_signed_get_rejects_tampered_token(client, db_session, regular_user, tmp_path):
    f, asset_name = _create_file_with_asset(db_session, regular_user, tmp_path)
    exp = int(time.time()) + 600
    token = build_signed_extract_asset_token(f.id, asset_name, exp)
    tampered = token[:-4] + "xxxx"

    resp = client.get(f"/api/files/signed-extract-assets/{tampered}")
    assert resp.status_code == 401


def test_signed_get_rejects_expired_token(client, db_session, regular_user, tmp_path):
    f, asset_name = _create_file_with_asset(db_session, regular_user, tmp_path)
    exp = int(time.time()) - 10
    token = build_signed_extract_asset_token(f.id, asset_name, exp)
    assert verify_signed_extract_asset_token(token) is None

    resp = client.get(f"/api/files/signed-extract-assets/{token}")
    assert resp.status_code == 401


def test_sign_rejects_invalid_asset_keys(client, db_session, regular_user, tmp_path):
    token = make_jwt(regular_user.id, regular_user.password_rev)
    f, _ = _create_file_with_asset(db_session, regular_user, tmp_path)

    resp = client.post(
        f"/api/files/{f.id}/extract-assets/sign",
        json={"asset_keys": ["../etc/passwd", "fig1.jpg"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "非法 asset_key" in resp.json()["detail"]


def test_signed_get_resolves_asset_without_hint_via_glob(client, db_session, regular_user):
    from config import UPLOAD_DIR
    from services.extract_asset_signing import build_signed_extract_asset_token
    from services.kb_figure_refs import extract_asset_abs_path_for_file_id

    rel_parent = os.path.join("globuser", "2026-07")
    abs_parent = os.path.join(UPLOAD_DIR, rel_parent)
    os.makedirs(abs_parent, exist_ok=True)
    f = FileModel(
        filename="glob.pdf",
        original_name="glob.pdf",
        file_path=os.path.join(abs_parent, "glob.pdf"),
        file_size=1,
        mime_type="application/pdf",
        user_id=regular_user.id,
        index_status="ready",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    assets = extract_assets_dir_for_file(f)
    images = os.path.join(assets, "images")
    os.makedirs(images, exist_ok=True)
    asset_name = "cold.jpg"
    with open(os.path.join(images, asset_name), "wb") as fh:
        fh.write(b"cold-path")

    assert extract_asset_abs_path_for_file_id(f.id, asset_name) is not None

    token = build_signed_extract_asset_token(f.id, asset_name, int(time.time()) + 600)
    resp = client.get(f"/api/files/signed-extract-assets/{token}")
    assert resp.status_code == 200
    assert resp.content == b"cold-path"


def test_legacy_extract_asset_forbidden_still_applies(client, db_session, regular_user, tmp_path):
    other = _create_user(db_session, "legacy-other-user")
    other_token = make_jwt(other.id, other.password_rev)
    f, asset_name = _create_file_with_asset(db_session, regular_user, tmp_path)

    resp = client.get(
        f"/api/files/{f.id}/extract-assets/{asset_name}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404
