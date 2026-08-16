# Copyright (c) 2026 徐泽宇
"""059 P2：用户组织（主部门、用户组）服务。"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.enterprise_rbac import Department, Group, UserGroup
from models.user import User


def _user_or_404(db: Session, user_id: int) -> User:
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return row


def _department_or_404(db: Session, department_id: int) -> Department:
    row = db.query(Department).filter(Department.id == department_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
    return row


def _load_user_groups(db: Session, user_id: int) -> list[dict]:
    rows = (
        db.query(Group.id, Group.name)
        .join(UserGroup, UserGroup.group_id == Group.id)
        .filter(UserGroup.user_id == user_id)
        .order_by(Group.name, Group.id)
        .all()
    )
    return [{"id": gid, "name": name} for gid, name in rows]


def _user_org_to_dict(db: Session, user: User, *, department: Department | None = None) -> dict:
    dept = department or _department_or_404(db, user.primary_department_id)
    return {
        "user_id": user.id,
        "primary_department_id": dept.id,
        "primary_department_name": dept.name,
        "groups": _load_user_groups(db, user.id),
    }


def get_user_org(db: Session, user_id: int) -> dict:
    user = _user_or_404(db, user_id)
    return _user_org_to_dict(db, user)


def update_user_org(
    db: Session,
    user_id: int,
    *,
    primary_department_id: int,
    group_ids: list[int],
) -> dict:
    user = _user_or_404(db, user_id)
    dept = _department_or_404(db, primary_department_id)

    unique_group_ids = list(dict.fromkeys(group_ids))
    if unique_group_ids:
        found_ids = {row[0] for row in db.query(Group.id).filter(Group.id.in_(unique_group_ids)).all()}
        missing = [gid for gid in unique_group_ids if gid not in found_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"用户组不存在: {', '.join(str(i) for i in missing)}",
            )

    user.primary_department_id = primary_department_id
    db.query(UserGroup).filter(UserGroup.user_id == user_id).delete(synchronize_session=False)
    for group_id in unique_group_ids:
        db.add(UserGroup(user_id=user_id, group_id=group_id))
    db.flush()
    return _user_org_to_dict(db, user, department=dept)
