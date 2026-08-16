# Copyright (c) 2026 徐泽宇
"""test_wechat_auth 模块。"""

import os

import pytest

from config import MOCK_WECHAT_OPENID
from models.user import User
from services.auth_service import hash_password
from services.enterprise_rbac_seed import get_unassigned_department_id


@pytest.fixture
def dev_env(monkeypatch):
    monkeypatch.setenv("FILEX_ENV", "development")
    monkeypatch.delenv("FILEX_WECHAT_APP_ID", raising=False)
    monkeypatch.delenv("FILEX_WECHAT_APP_SECRET", raising=False)
    monkeypatch.delenv("FILEX_WECHAT_REDIRECT_URI", raising=False)


def _qrcode(client):
    resp = client.get("/api/wechat/qrcode")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"]
    assert data["poll_token"]
    assert data["mock_mode"] is True
    return data["state"], data["poll_token"]


def _status(client, state: str, poll_token: str | None = None):
    params = {"poll_token": poll_token} if poll_token else None
    return client.get(f"/api/wechat/status/{state}", params=params)


def test_qrcode_mock_mode(client, dev_env):
    state, _poll = _qrcode(client)
    assert len(state) >= 32


def test_status_without_poll_does_not_leak_token(client, db_session, dev_env):
    from fastapi.testclient import TestClient

    user = User(
        username="wx_poll_guard",
        password_hash=hash_password("secret12"),
        is_admin=False,
        wechat_openid=MOCK_WECHAT_OPENID,
        primary_department_id=get_unassigned_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()

    state, poll_token = _qrcode(client)
    client.get("/api/wechat/mock-callback", params={"state": state, "scenario": "login"})

    attacker = TestClient(client.app)
    leaked = attacker.get(f"/api/wechat/status/{state}")
    assert leaked.status_code == 200
    assert leaked.json()["status"] == "pending"
    assert "access_token" not in leaked.json()

    authed = _status(client, state, poll_token=poll_token)
    assert authed.status_code == 200
    body = authed.json()
    assert body["status"] == "success"
    assert body["access_token"]


def test_mock_need_register_flow(client, db_session, dev_env):
    state, poll_token = _qrcode(client)
    resp = client.get("/api/wechat/mock-callback", params={"state": state, "scenario": "need_register"})
    assert resp.status_code == 200

    status_resp = _status(client, state, poll_token=poll_token)
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "need_register"

    reg = client.post(
        "/api/auth/register",
        json={"username": "wx_new_user", "password": "secret12", "wechat_state": state},
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["wechat_bound"] is True

    user = db_session.query(User).filter(User.username == "wx_new_user").first()
    assert user is not None
    assert user.wechat_openid == MOCK_WECHAT_OPENID


def test_mock_login_existing_user(client, db_session, dev_env):
    user = User(
        username="wx_linked",
        password_hash=hash_password("secret12"),
        is_admin=False,
        wechat_openid=MOCK_WECHAT_OPENID,
        primary_department_id=get_unassigned_department_id(db_session),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    state, poll_token = _qrcode(client)
    resp = client.get("/api/wechat/mock-callback", params={"state": state, "scenario": "login"})
    assert resp.status_code == 200

    status_resp = _status(client, state, poll_token=poll_token)
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "success"
    assert body["access_token"]
    assert body["user"]["username"] == "wx_linked"


def test_bind_wechat(client, db_session, jwt_token, regular_user, dev_env):
    me0 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {jwt_token}"})
    assert me0.json()["wechat_bound"] is False

    bind = client.get("/api/wechat/bind-qrcode", headers={"Authorization": f"Bearer {jwt_token}"})
    assert bind.status_code == 200
    state = bind.json()["state"]
    poll_token = bind.json()["poll_token"]

    resp = client.get("/api/wechat/mock-callback", params={"state": state, "scenario": "login"})
    assert resp.status_code == 200

    status_resp = _status(client, state, poll_token=poll_token)
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "awaiting_bind_confirm"

    confirm = client.post(
        "/api/wechat/confirm-bind",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"state": state, "poll_token": poll_token},
    )
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "success"

    db_session.refresh(regular_user)
    assert regular_user.wechat_openid == MOCK_WECHAT_OPENID

    me1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {jwt_token}"})
    assert me1.json()["wechat_bound"] is True


def test_bind_wechat_conflict_returns_error_html_and_status(client, db_session, jwt_token, dev_env):
    other = User(
        username="wx_other_bound",
        password_hash=hash_password("secret12"),
        is_admin=False,
        wechat_openid=MOCK_WECHAT_OPENID,
        primary_department_id=get_unassigned_department_id(db_session),
    )
    db_session.add(other)
    db_session.commit()

    bind = client.get("/api/wechat/bind-qrcode", headers={"Authorization": f"Bearer {jwt_token}"})
    assert bind.status_code == 200
    state = bind.json()["state"]
    poll_token = bind.json()["poll_token"]

    resp = client.get("/api/wechat/mock-callback", params={"state": state, "scenario": "login"})
    assert resp.status_code == 200
    assert "application/json" not in (resp.headers.get("content-type") or "")
    assert "该微信账号已绑定到其他用户" in resp.text

    status_resp = _status(client, state, poll_token=poll_token)
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "error"
    assert body["message"] == "该微信账号已绑定到其他用户"


def test_register_rejects_reused_wechat_state(client, db_session, dev_env):
    state, poll_token = _qrcode(client)
    client.get("/api/wechat/mock-callback", params={"state": state, "scenario": "need_register"})

    first = client.post(
        "/api/auth/register",
        json={"username": "wx_once", "password": "secret12", "wechat_state": state},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/auth/register",
        json={"username": "wx_twice", "password": "secret12", "wechat_state": state},
    )
    assert second.status_code == 400
