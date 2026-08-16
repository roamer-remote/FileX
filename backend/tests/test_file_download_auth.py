# Copyright (c) 2026 徐泽宇
"""Download/preview require credentials and enforce per-user file ownership.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

import pytest
from fastapi import status

from middleware.auth import FILE_STREAM_AUTH_REQUIRED_DETAIL
from models.file import File as FileModel
from tests.conftest import _create_api_key, _create_user


@pytest.fixture
def downloadable_file(db_session, regular_user, tmp_path):
    path = tmp_path / "secret.bin"
    path.write_bytes(b"owned-by-testuser")
    f = FileModel(
        filename="secret.bin",
        original_name="secret.bin",
        file_path=str(path),
        file_size=path.stat().st_size,
        mime_type="application/octet-stream",
        user_id=regular_user.id,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


@pytest.fixture
def other_user_file(db_session, downloadable_file):
    other = _create_user(db_session, "otherdl")
    f = FileModel(
        filename="other.bin",
        original_name="other.bin",
        file_path=downloadable_file.file_path,
        file_size=10,
        mime_type="application/octet-stream",
        user_id=other.id,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f, other


def test_download_without_credentials_401(client, downloadable_file):
    r = client.get(f"/api/files/{downloadable_file.id}/download")
    assert r.status_code == status.HTTP_401_UNAUTHORIZED
    assert r.json()["detail"] == FILE_STREAM_AUTH_REQUIRED_DETAIL


def test_download_other_user_file_404(client, jwt_token, other_user_file):
    other_file, _ = other_user_file
    r = client.get(
        f"/api/files/{other_file.id}/download",
        params={"token": jwt_token},
    )
    assert r.status_code == status.HTTP_404_NOT_FOUND


def test_download_own_file_with_query_token(client, jwt_token, downloadable_file):
    r = client.get(
        f"/api/files/{downloadable_file.id}/download",
        params={"token": jwt_token},
    )
    assert r.status_code == status.HTTP_200_OK
    assert r.content == b"owned-by-testuser"


def test_download_own_file_with_bearer_header(client, jwt_token, downloadable_file):
    r = client.get(
        f"/api/files/{downloadable_file.id}/download",
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == status.HTTP_200_OK


def test_download_own_file_with_api_key(client, db_session, regular_user, downloadable_file):
    key = _create_api_key(db_session, regular_user)
    r = client.get(
        f"/api/files/{downloadable_file.id}/download",
        headers={"Authorization": f"Bearer {key._plaintext}"},
    )
    assert r.status_code == status.HTTP_200_OK
