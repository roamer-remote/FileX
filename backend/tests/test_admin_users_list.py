# Copyright (c) 2026 徐泽宇
"""Admin user list pagination.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from fastapi import status


def test_admin_users_paginated(client, admin_jwt_token, db_session, regular_user):
    h = {"Authorization": f"Bearer {admin_jwt_token}"}
    resp = client.get("/api/admin/users", headers=h, params={"page": 1, "page_size": 1})
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert len(data["items"]) == 1
    assert data["total"] >= 2
    assert "summary" in data
    assert isinstance(data["summary"]["admin_count"], int)
    assert isinstance(data["summary"]["active_today_count"], int)
