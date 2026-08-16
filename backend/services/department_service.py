# Copyright (c) 2026 徐泽宇
"""059 P2：部门树 CRUD 服务。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.enterprise_rbac import (
    DEPARTMENT_ROOT_NAME,
    DEPARTMENT_UNASSIGNED_NAME,
    SUBJECT_DEPARTMENT,
    Department,
    FolderAcl,
)
from models.user import User
from utils.timezone import to_beijing_time


class DepartmentDeleteConflictError(Exception):
    """删除部门冲突（含 ACL 引用时需返回 affected_acl_ids）。"""

    def __init__(self, detail: str, *, affected_acl_ids: list[int] | None = None):
        super().__init__(detail)
        self.detail = detail
        self.affected_acl_ids = affected_acl_ids or []


def _department_or_404(db: Session, department_id: int) -> Department:
    row = db.query(Department).filter(Department.id == department_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
    return row


def _is_protected_department(dept: Department) -> bool:
    return dept.name in (DEPARTMENT_ROOT_NAME, DEPARTMENT_UNASSIGNED_NAME)


def _department_to_dict(dept: Department) -> dict:
    return {
        "id": dept.id,
        "name": dept.name,
        "parent_id": dept.parent_id,
        "sort_order": dept.sort_order,
        "created_at": to_beijing_time(dept.created_at).isoformat() if dept.created_at else "",
        "is_builtin": _is_protected_department(dept),
    }


def list_departments(db: Session) -> list[dict]:
    rows = db.query(Department).order_by(Department.parent_id.nullsfirst(), Department.sort_order, Department.id).all()
    return [_department_to_dict(d) for d in rows]


def _would_create_cycle(db: Session, dept_id: int, new_parent_id: int | None) -> bool:
    if new_parent_id is None:
        return False
    if new_parent_id == dept_id:
        return True
    seen: set[int] = set()
    cur = new_parent_id
    while cur is not None:
        if cur == dept_id:
            return True
        if cur in seen:
            break
        seen.add(cur)
        parent = db.query(Department.parent_id).filter(Department.id == cur).scalar()
        cur = int(parent) if parent is not None else None
    return False


def create_department(db: Session, *, name: str, parent_id: int, sort_order: int = 0) -> dict:
    parent = _department_or_404(db, parent_id)
    if parent.name == DEPARTMENT_UNASSIGNED_NAME:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不可在「未分配」下创建子部门")
    dept = Department(name=name.strip(), parent_id=parent_id, sort_order=sort_order)
    db.add(dept)
    db.flush()
    return _department_to_dict(dept)


def update_department(
    db: Session,
    department_id: int,
    *,
    name: str | None = None,
    parent_id: int | None = None,
    sort_order: int | None = None,
) -> dict:
    dept = _department_or_404(db, department_id)
    if _is_protected_department(dept):
        if name is not None and name.strip() != dept.name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="内置部门不可重命名")
        if parent_id is not None and parent_id != dept.parent_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="内置部门不可移动")
    if name is not None:
        dept.name = name.strip()
    if sort_order is not None:
        dept.sort_order = sort_order
    if parent_id is not None:
        if dept.parent_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="根部门不可指定父节点")
        if parent_id != dept.parent_id:
            new_parent = _department_or_404(db, parent_id)
            if new_parent.name == DEPARTMENT_UNASSIGNED_NAME:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="不可将部门移至「未分配」下",
                )
            if _would_create_cycle(db, dept.id, parent_id):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="父部门不能为自身或子部门")
            dept.parent_id = parent_id
    db.flush()
    return _department_to_dict(dept)


def delete_department(db: Session, department_id: int) -> None:
    dept = _department_or_404(db, department_id)
    if _is_protected_department(dept):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="内置部门不可删除")

    child_count = db.query(Department.id).filter(Department.parent_id == department_id).count()
    if child_count:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该部门存在子部门，请先移除或迁移")

    user_count = db.query(User.id).filter(User.primary_department_id == department_id).count()
    if user_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"该部门仍有 {user_count} 名用户的主部门，请先迁移用户",
        )

    acl_rows = (
        db.query(FolderAcl.id)
        .filter(FolderAcl.subject_type == SUBJECT_DEPARTMENT, FolderAcl.subject_id == department_id)
        .all()
    )
    if acl_rows:
        acl_ids = [int(r[0]) for r in acl_rows]
        raise DepartmentDeleteConflictError(
            f"该部门在 {len(acl_ids)} 条目录 ACL 中被引用，请先移除",
            affected_acl_ids=acl_ids,
        )

    db.delete(dept)
    db.flush()
