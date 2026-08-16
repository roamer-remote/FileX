# Copyright (c) 2026 徐泽宇
"""测试 /api/admin/mineru-version 端点（纯中继 MinerU sidecar 版本）。"""

from unittest.mock import MagicMock, patch

import config
import httpx


def test_admin_mineru_version_success(client, admin_jwt_token, monkeypatch):
    monkeypatch.setattr(config, "KB_EXTRACT_MINERU_URL", "http://mineru.test:8080")
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    fake_resp = MagicMock(spec=httpx.Response)
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"mineru_version": "2.5.4", "sidecar_version": "0.1.0"}

    with patch("backend.routers.admin.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value = fake_resp
        mock_client_cls.return_value = mock_client

        r = client.get("/api/admin/mineru-version", headers=headers)

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mineru_version"] == "2.5.4"
    assert data["sidecar_version"] == "0.1.0"
    mock_client_cls.assert_called_once_with(timeout=2.0, trust_env=False)


def test_admin_mineru_version_timeout_returns_unknown(client, admin_jwt_token, monkeypatch):
    monkeypatch.setattr(config, "KB_EXTRACT_MINERU_URL", "http://mineru.test:8080")
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    with patch("backend.routers.admin.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.side_effect = httpx.TimeoutException("timeout")
        mock_client_cls.return_value = mock_client

        r = client.get("/api/admin/mineru-version", headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["mineru_version"] is None
    assert data["sidecar_version"] is None
    assert data.get("error") is not None


def test_admin_mineru_version_non_200_returns_unknown(client, admin_jwt_token, monkeypatch):
    monkeypatch.setattr(config, "KB_EXTRACT_MINERU_URL", "http://mineru.test:8080")
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    fake_resp = MagicMock(spec=httpx.Response)
    fake_resp.status_code = 503
    fake_resp.json.return_value = {}

    with patch("backend.routers.admin.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value = fake_resp
        mock_client_cls.return_value = mock_client

        r = client.get("/api/admin/mineru-version", headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["mineru_version"] is None
    assert data.get("error") is not None


def test_admin_mineru_version_missing_field_returns_nulls(client, admin_jwt_token, monkeypatch):
    monkeypatch.setattr(config, "KB_EXTRACT_MINERU_URL", "http://mineru.test:8080")
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    fake_resp = MagicMock(spec=httpx.Response)
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"status": "ok"}  # 缺少版本字段

    with patch("backend.routers.admin.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value.get.return_value = fake_resp
        mock_client_cls.return_value = mock_client

        r = client.get("/api/admin/mineru-version", headers=headers)

    assert r.status_code == 200
    data = r.json()
    # 端点透传，缺失时为 None
    assert data.get("mineru_version") is None


def test_admin_mineru_version_no_url_config_returns_error(client, admin_jwt_token, monkeypatch):
    headers = {"Authorization": f"Bearer {admin_jwt_token}"}

    # 由于函数内 from config import，这里直接 patch config 模块属性
    monkeypatch.setattr(config, "KB_EXTRACT_MINERU_URL", "")

    r = client.get("/api/admin/mineru-version", headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["mineru_version"] is None
    assert "KB_EXTRACT_MINERU_URL" in (data.get("error") or "") or "未配置" in (data.get("error") or "")
