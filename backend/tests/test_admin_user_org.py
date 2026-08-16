# Copyright (c) 2026 徐泽宇
"""059 P2 T-15：管理员用户组织（主部门、组）。"""

from __future__ import annotations

from fastapi import status

from models.enterprise_rbac import Department, Group, UserGroup
from services.enterprise_rbac_seed import get_unassigned_department_id


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _root_department(db_session) -> Department:
    return db_session.query(Department).filter(Department.parent_id.is_(None)).one()


def test_non_admin_forbidden(client, jwt_token, regular_user):
    r = client.get(f"/api/admin/users/{regular_user.id}/org", headers=_auth(jwt_token))
    assert r.status_code == status.HTTP_403_FORBIDDEN


def test_get_and_put_user_org(client, admin_jwt_token, db_session, regular_user):
    root = _root_department(db_session)
    dept = Department(name="研发部", parent_id=root.id, sort_order=1)
    g1 = Group(name="前端组", description=None)
    g2 = Group(name="后端组", description=None)
    db_session.add_all([dept, g1, g2])
    db_session.commit()
    db_session.refresh(dept)
    db_session.refresh(g1)
    db_session.refresh(g2)

    r = client.put(
        f"/api/admin/users/{regular_user.id}/org",
        headers=_auth(admin_jwt_token),
        json={"primary_department_id": dept.id, "group_ids": [g1.id, g2.id]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == regular_user.id
    assert body["primary_department_id"] == dept.id
    assert body["primary_department_name"] == "研发部"
    assert {g["id"] for g in body["groups"]} == {g1.id, g2.id}

    r2 = client.get(f"/api/admin/users/{regular_user.id}/org", headers=_auth(admin_jwt_token))
    assert r2.status_code == 200
    assert r2.json()["primary_department_id"] == dept.id
    assert len(r2.json()["groups"]) == 2

    db_session.refresh(regular_user)
    assert regular_user.primary_department_id == dept.id


def test_put_user_org_replaces_group_membership(client, admin_jwt_token, db_session, regular_user):
    root = _root_department(db_session)
    g_old = Group(name="旧组", description=None)
    g_new = Group(name="新组", description=None)
    db_session.add_all([g_old, g_new])
    db_session.flush()
    db_session.add(UserGroup(user_id=regular_user.id, group_id=g_old.id))
    db_session.commit()
    db_session.refresh(g_new)

    unassigned_id = get_unassigned_department_id(db_session)
    r = client.put(
        f"/api/admin/users/{regular_user.id}/org",
        headers=_auth(admin_jwt_token),
        json={"primary_department_id": unassigned_id, "group_ids": [g_new.id]},
    )
    assert r.status_code == 200
    assert len(r.json()["groups"]) == 1
    assert r.json()["groups"][0]["id"] == g_new.id

    rows = (
        db_session.query(UserGroup.group_id)
        .filter(UserGroup.user_id == regular_user.id)
        .all()
    )
    assert [int(x[0]) for x in rows] == [g_new.id]


def test_put_user_org_clears_groups(client, admin_jwt_token, db_session, regular_user):
    g = Group(name="待清除组", description=None)
    db_session.add(g)
    db_session.flush()
    db_session.add(UserGroup(user_id=regular_user.id, group_id=g.id))
    db_session.commit()

    unassigned_id = get_unassigned_department_id(db_session)
    r = client.put(
        f"/api/admin/users/{regular_user.id}/org",
        headers=_auth(admin_jwt_token),
        json={"primary_department_id": unassigned_id, "group_ids": []},
    )
    assert r.status_code == 200
    assert r.json()["groups"] == []
    assert (
        db_session.query(UserGroup).filter(UserGroup.user_id == regular_user.id).count() == 0
    )


def test_put_user_org_invalid_department(client, admin_jwt_token, regular_user):
    r = client.put(
        f"/api/admin/users/{regular_user.id}/org",
        headers=_auth(admin_jwt_token),
        json={"primary_department_id": 999999, "group_ids": []},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "部门不存在"


def test_put_user_org_invalid_group(client, admin_jwt_token, db_session, regular_user):
    unassigned_id = get_unassigned_department_id(db_session)
    r = client.put(
        f"/api/admin/users/{regular_user.id}/org",
        headers=_auth(admin_jwt_token),
        json={"primary_department_id": unassigned_id, "group_ids": [888888]},
    )
    assert r.status_code == 400
    assert "用户组不存在" in r.json()["detail"]


def test_get_user_org_not_found(client, admin_jwt_token):
    r = client.get("/api/admin/users/999999/org", headers=_auth(admin_jwt_token))
    assert r.status_code == 404
    assert r.json()["detail"] == "用户不存在"


def test_put_user_org_deduplicates_group_ids(client, admin_jwt_token, db_session, regular_user):
    g = Group(name="重复组", description=None)
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    unassigned_id = get_unassigned_department_id(db_session)

    r = client.put(
        f"/api/admin/users/{regular_user.id}/org",
        headers=_auth(admin_jwt_token),
        json={"primary_department_id": unassigned_id, "group_ids": [g.id, g.id, g.id]},
    )
    assert r.status_code == 200
    assert len(r.json()["groups"]) == 1
