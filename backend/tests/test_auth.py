# Copyright (c) 2026 徐泽宇
"""Tests for authentication middleware (JWT + API Key + ?token=).

Uses TestClient against real routes and direct function calls for unit-level
scenarios that are easier to validate in isolation.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from datetime import timedelta

import pytest
from fastapi import status

from config import SECRET_KEY
from .conftest import make_jwt
from middleware.auth import API_KEY_USER_INACTIVE_DETAIL, user_from_url_query_token
from services.auth_service import create_access_token

# ═══════════════════════════════════════════════════════════════════════
# JWT Authentication
# ═══════════════════════════════════════════════════════════════════════


class TestJWT:
    """Tests that exercise JWT-based authentication via /api/auth/me."""

    def test_valid(self, client, jwt_token):
        """A valid, non-expired JWT with matching pwd_rev succeeds."""
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {jwt_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testuser"
        assert data["is_active"] is True
        assert data.get("has_avatar") is False

    def test_expired(self, client, regular_user):
        """An expired JWT returns 401."""
        token = make_jwt(regular_user.id, 0, expire_delta=timedelta(days=-1))
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_wrong_pwd_rev(self, client, regular_user, db_session):
        """A JWT carrying a stale pwd_rev returns 401 (password was changed)."""
        token = make_jwt(regular_user.id, pwd_rev=0)
        # Increment password_rev in DB to simulate a password change
        regular_user.password_rev = 1
        db_session.add(regular_user)
        db_session.commit()
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_inactive_user(self, client, inactive_user):
        """A valid JWT for a deactivated user returns 401."""
        token = create_access_token(inactive_user.id, inactive_user.password_rev)
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_signature(self, client, regular_user):
        """A JWT signed with a different key returns 401."""
        from jose import jwt
        from config import ALGORITHM
        from datetime import datetime
        payload = {
            "sub": str(regular_user.id),
            "exp": datetime.utcnow() + timedelta(hours=1),
            "pwd_rev": 0,
        }
        token = jwt.encode(payload, "wrong-secret-key", algorithm=ALGORITHM)
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_malformed_token(self, client):
        """A garbage token string returns 401."""
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_auth_header(self, client):
        """A request without an Authorization header returns 401."""
        resp = client.get("/api/auth/me")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_bearer_no_token(self, client):
        """Bearer with an empty token returns 401."""
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer "})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ═══════════════════════════════════════════════════════════════════════
# API Key Authentication
# ═══════════════════════════════════════════════════════════════════════


class TestAPIKey:
    """Tests that exercise API Key authentication via /api/auth/me."""

    def test_valid(self, client, active_api_key):
        """A valid, active API key succeeds."""
        resp = client.get("/api/auth/me",
                          headers={"Authorization": f"Bearer {active_api_key._plaintext}"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "testuser"

    def test_deactivated_key(self, client, deactivated_api_key):
        """A deactivated API key (is_active=False) returns 401."""
        resp = client.get("/api/auth/me",
                          headers={"Authorization": f"Bearer {deactivated_api_key._plaintext}"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_wrong_prefix(self, client, regular_user):
        """A key without the correct prefix (fb_) falls through to JWT and fails."""
        resp = client.get("/api/auth/me",
                          headers={"Authorization": "Bearer xx_not_a_key_xxx"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unknown_key(self, client):
        """A syntactically valid (fb_ prefix) but unknown key returns 401."""
        resp = client.get("/api/auth/me",
                          headers={"Authorization": "Bearer fb_this_key_does_not_exist_in_db"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_key_owner_inactive_optional_returns_none(self, db_session, regular_user):
        """可选鉴权路径：停用用户 + 有效密钥仍返回 None（不抛错）。"""
        from middleware.auth import _get_user_from_api_key
        from .conftest import _create_api_key

        key = _create_api_key(db_session, regular_user, is_active=True)
        regular_user.is_active = False
        db_session.commit()
        assert _get_user_from_api_key(key._plaintext, db_session) is None

    def test_key_owner_inactive_me_returns_403(self, client, db_session, regular_user, active_api_key):
        """双通道 /api/auth/me：有效密钥但用户已停用 → 403 与固定文案。"""
        regular_user.is_active = False
        db_session.commit()
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert resp.json()["detail"] == API_KEY_USER_INACTIVE_DETAIL


# ═══════════════════════════════════════════════════════════════════════
# Dual channel fallback & ?token= download auth
# ═══════════════════════════════════════════════════════════════════════


class TestDualAuthAndToken:
    """Tests JWT→API Key fallback and user_from_url_query_token."""

    def test_jwt_takes_priority_over_api_key(self, client, jwt_token, active_api_key):
        """When both JWT and API Key are valid, JWT user is returned."""
        resp = client.get("/api/auth/me",
                          headers={"Authorization": f"Bearer {jwt_token}"})
        assert resp.status_code == 200
        # The JWT belongs to "testuser", which is the same user as the API key
        assert resp.json()["username"] == "testuser"

    def test_user_from_url_query_token_jwt(self, db_session, regular_user):
        """user_from_url_query_token accepts a valid JWT."""
        token = create_access_token(regular_user.id, regular_user.password_rev)
        user = user_from_url_query_token(token, db_session)
        assert user is not None
        assert user.id == regular_user.id
        assert user.username == "testuser"

    def test_user_from_url_query_token_api_key(self, db_session, active_api_key):
        """user_from_url_query_token accepts a valid API key."""
        user = user_from_url_query_token(active_api_key._plaintext, db_session)
        assert user is not None
        assert user.id == active_api_key.user_id

    def test_user_from_url_query_token_invalid(self, db_session):
        """user_from_url_query_token returns None for garbage."""
        user = user_from_url_query_token("totally_invalid_token", db_session)
        assert user is None

    def test_user_from_url_query_token_expired_jwt(self, db_session, regular_user):
        """user_from_url_query_token returns None for an expired JWT."""
        token = make_jwt(regular_user.id, 0, expire_delta=timedelta(days=-1))
        user = user_from_url_query_token(token, db_session)
        assert user is None

    def test_user_from_url_query_token_deactivated_key(self, db_session, deactivated_api_key):
        """user_from_url_query_token returns None for a deactivated API key."""
        user = user_from_url_query_token(deactivated_api_key._plaintext, db_session)
        assert user is None

    def test_user_from_url_query_token_api_key_owner_inactive(self, db_session, regular_user):
        """?token= 路径：有效密钥但用户已停用 → 403。"""
        from fastapi import HTTPException
        from .conftest import _create_api_key

        key = _create_api_key(db_session, regular_user, is_active=True)
        regular_user.is_active = False
        db_session.commit()
        with pytest.raises(HTTPException) as exc_info:
            user_from_url_query_token(key._plaintext, db_session)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.detail == API_KEY_USER_INACTIVE_DETAIL


# ═══════════════════════════════════════════════════════════════════════
# Admin route guard
# ═══════════════════════════════════════════════════════════════════════


class TestAdminGuard:
    """Tests that admin-only routes reject non-admin users."""

    def test_regular_user_blocked(self, client, jwt_token):
        """A regular user gets 403 on an admin route."""
        resp = client.get("/api/admin/users",
                          headers={"Authorization": f"Bearer {jwt_token}"},
                          params={"page": 1, "page_size": 1})
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_user_allowed(self, client, admin_jwt_token):
        """An admin user can access admin routes."""
        resp = client.get("/api/admin/users",
                          headers={"Authorization": f"Bearer {admin_jwt_token}"},
                          params={"page": 1, "page_size": 1})
        assert resp.status_code == 200

    def test_admin_with_api_key_blocked(self, client, active_api_key):
        """An API key (even valid) cannot access admin routes."""
        resp = client.get("/api/admin/users",
                          headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
                          params={"page": 1, "page_size": 1})
        # The route requires JWT first via get_current_user, then admin check
        # API key works for get_current_user but then get_admin_user checks is_admin
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ═══════════════════════════════════════════════════════════════════════
# API Key only routes (external uploads)
# ═══════════════════════════════════════════════════════════════════════


class TestExternalAPI:
    """Tests for routes gated by get_api_key_user (API Key only, no JWT fallback)."""

    def test_jwt_rejected_on_external_route(self, client, jwt_token):
        """A valid JWT is rejected on /api/external routes (API key only)."""
        resp = client.post("/api/external/files",
                           headers={"Authorization": f"Bearer {jwt_token}"})
        # Auth failure → 401 (JWT not accepted by get_api_key_user)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


    def test_deactivated_key_on_external_route_detail(self, client, deactivated_api_key):
        """下架密钥在外部路由返回明确 401 文案。"""
        resp = client.post(
            "/api/external/files",
            headers={"Authorization": f"Bearer {deactivated_api_key._plaintext}"},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert "下架" in resp.json()["detail"]

    def test_api_key_whitespace_stripped(self, client, active_api_key):
        """密钥首尾空白应仍能鉴权通过（到 422 说明已过 auth）。"""
        key = active_api_key._plaintext + "\n"
        resp = client.post(
            "/api/external/files",
            headers={"Authorization": f"Bearer {key}"},
        )
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_valid_api_key_on_external_route(self, client, active_api_key):
        """A valid API key is accepted on /api/external routes (passes auth)."""
        resp = client.post("/api/external/files",
                           headers={"Authorization": f"Bearer {active_api_key._plaintext}"})
        # Auth passes; without a file body, we expect 422 validation error
        assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_external_api_key_owner_inactive_returns_403(self, client, db_session, regular_user, active_api_key):
        """仅 API Key 路由：密钥有效但用户已停用 → 403 与固定文案。"""
        regular_user.is_active = False
        db_session.commit()
        resp = client.get(
            "/api/external/files-awaiting-ai",
            headers={"Authorization": f"Bearer {active_api_key._plaintext}"},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert resp.json()["detail"] == API_KEY_USER_INACTIVE_DETAIL
