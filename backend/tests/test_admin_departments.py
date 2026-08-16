# Copyright (c) 2026 徐泽宇
"""059 P2 T-12：管理员部门 CRUD + T-27m ACL 删除冲突。"""

from __future__ import annotations

from fastapi import status

from models.enterprise_rbac import (
    DEPARTMENT_ROOT_NAME,
    DEPARTMENT_UNASSIGNED_NAME,
    PERM_READ,
    SUBJECT_DEPARTMENT,
    Department,
    FolderAcl,
)
from services.workspace_service import create_shared_workspace


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _root_department(db_session) -> Department:
    return (
        db_session.query(Department)
        .filter(Department.parent_id.is_(None), Department.name == DEPARTMENT_ROOT_NAME)
        .one()
    )


def _unassigned_department(db_session) -> Department:
    return db_session.query(Department).filter(Department.name == DEPARTMENT_UNASSIGNED_NAME).one()


def test_non_admin_forbidden(client, jwt_token):
    r = client.get("/api/admin/departments", headers=_auth(jwt_token))
    assert r.status_code == status.HTTP_403_FORBIDDEN


def test_admin_list_departments_includes_builtin(client, admin_jwt_token, db_session):
    r = client.get("/api/admin/departments", headers=_auth(admin_jwt_token))
    assert r.status_code == 200
    items = r.json()
    names = {d["name"] for d in items}
    assert DEPARTMENT_ROOT_NAME in names
    assert DEPARTMENT_UNASSIGNED_NAME in names
    root = next(d for d in items if d["name"] == DEPARTMENT_ROOT_NAME)
    assert root["parent_id"] is None
    assert root["is_builtin"] is True


def test_admin_create_update_delete_department(client, admin_jwt_token, db_session):
    root = _root_department(db_session)
    r = client.post(
        "/api/admin/departments",
        headers=_auth(admin_jwt_token),
        json={"name": "研发部", "parent_id": root.id, "sort_order": 10},
    )
    assert r.status_code == 201
    dept_id = r.json()["id"]
    assert r.json()["name"] == "研发部"
    assert r.json()["parent_id"] == root.id

    r2 = client.put(
        f"/api/admin/departments/{dept_id}",
        headers=_auth(admin_jwt_token),
        json={"name": "研发中心", "sort_order": 20},
    )
    assert r2.status_code == 200
    assert r2.json()["name"] == "研发中心"
    assert r2.json()["sort_order"] == 20

    r3 = client.delete(f"/api/admin/departments/{dept_id}", headers=_auth(admin_jwt_token))
    assert r3.status_code == 204


def test_cannot_create_under_unassigned(client, admin_jwt_token, db_session):
    unassigned = _unassigned_department(db_session)
    r = client.post(
        "/api/admin/departments",
        headers=_auth(admin_jwt_token),
        json={"name": "非法子部门", "parent_id": unassigned.id},
    )
    assert r.status_code == 400
    assert "未分配" in r.json()["detail"]


def test_cannot_delete_builtin_departments(client, admin_jwt_token, db_session):
    root = _root_department(db_session)
    unassigned = _unassigned_department(db_session)
    for dept_id in (root.id, unassigned.id):
        r = client.delete(f"/api/admin/departments/{dept_id}", headers=_auth(admin_jwt_token))
        assert r.status_code == 400
        assert "内置" in r.json()["detail"]


def test_delete_department_with_children_returns_409(client, admin_jwt_token, db_session):
    root = _root_department(db_session)
    parent = Department(name="父部门", parent_id=root.id, sort_order=1)
    db_session.add(parent)
    db_session.flush()
    child = Department(name="子部门", parent_id=parent.id, sort_order=1)
    db_session.add(child)
    db_session.commit()

    r = client.delete(f"/api/admin/departments/{parent.id}", headers=_auth(admin_jwt_token))
    assert r.status_code == 409
    assert "子部门" in r.json()["detail"]


def test_delete_department_with_users_returns_409(client, admin_jwt_token, db_session, regular_user):
    root = _root_department(db_session)
    dept = Department(name="有人部门", parent_id=root.id, sort_order=1)
    db_session.add(dept)
    db_session.flush()
    regular_user.primary_department_id = dept.id
    db_session.add(regular_user)
    db_session.commit()

    r = client.delete(f"/api/admin/departments/{dept.id}", headers=_auth(admin_jwt_token))
    assert r.status_code == 409
    assert "用户" in r.json()["detail"]


def test_delete_department_with_acl_returns_409_and_affected_acls(
    client, admin_jwt_token, db_session, regular_user
):
    """T-27m：删部门有 folder_acl 引用 → 409 + affected_acl_ids。"""
    root = _root_department(db_session)
    dept = Department(name="ACL 部门", parent_id=root.id, sort_order=1)
    db_session.add(dept)
    db_session.flush()

    shared = create_shared_workspace(db_session, name="部门 ACL 测试库", owner=regular_user)
    acl = FolderAcl(
        workspace_id=shared.id,
        folder_id=None,
        subject_type=SUBJECT_DEPARTMENT,
        subject_id=dept.id,
        permission=PERM_READ,
    )
    db_session.add(acl)
    db_session.commit()
    db_session.refresh(acl)

    r = client.delete(f"/api/admin/departments/{dept.id}", headers=_auth(admin_jwt_token))
    assert r.status_code == 409
    body = r.json()
    assert "ACL" in body["detail"]
    assert body["affected_acl_ids"] == [acl.id]

    still = db_session.get(Department, dept.id)
    assert still is not None


def test_update_department_rejects_cycle(client, admin_jwt_token, db_session):
    root = _root_department(db_session)
    parent = Department(name="A", parent_id=root.id, sort_order=1)
    db_session.add(parent)
    db_session.flush()
    child = Department(name="B", parent_id=parent.id, sort_order=1)
    db_session.add(child)
    db_session.commit()

    r = client.put(
        f"/api/admin/departments/{parent.id}",
        headers=_auth(admin_jwt_token),
        json={"parent_id": child.id},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "父部门不能为自身或子部门"


def test_cannot_move_under_unassigned(client, admin_jwt_token, db_session):
    root = _root_department(db_session)
    unassigned = _unassigned_department(db_session)
    dept = Department(name="可移动部门", parent_id=root.id, sort_order=1)
    db_session.add(dept)
    db_session.commit()

    r = client.put(
        f"/api/admin/departments/{dept.id}",
        headers=_auth(admin_jwt_token),
        json={"parent_id": unassigned.id},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "不可将部门移至「未分配」下"


def test_update_builtin_department_rejects_rename_and_move(client, admin_jwt_token, db_session):
    root = _root_department(db_session)

    r_same = client.put(
        f"/api/admin/departments/{root.id}",
        headers=_auth(admin_jwt_token),
        json={"name": DEPARTMENT_ROOT_NAME},
    )
    assert r_same.status_code == 200
    assert r_same.json()["name"] == DEPARTMENT_ROOT_NAME

    r_rename = client.put(
        f"/api/admin/departments/{root.id}",
        headers=_auth(admin_jwt_token),
        json={"name": "新组织名"},
    )
    assert r_rename.status_code == 400
    assert r_rename.json()["detail"] == "内置部门不可重命名"

    child = Department(name="试探子部门", parent_id=root.id, sort_order=99)
    db_session.add(child)
    db_session.commit()

    r_move = client.put(
        f"/api/admin/departments/{root.id}",
        headers=_auth(admin_jwt_token),
        json={"parent_id": child.id},
    )
    assert r_move.status_code == 400
    assert r_move.json()["detail"] == "内置部门不可移动"
