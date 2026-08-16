# Copyright (c) 2026 徐泽宇
"""059 P2 T-13：管理员用户组 CRUD。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_admin_user
from models.user import User
from schemas.admin_rbac import GroupCreateRequest, GroupResponse, GroupUpdateRequest
from services.group_service import (
    GroupDeleteConflictError,
    create_group,
    delete_group,
    list_groups,
    update_group,
)
from services.log_service import log_operation

router = APIRouter()


@router.get("", response_model=list[GroupResponse])
def admin_list_groups(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return list_groups(db)


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def admin_create_group(
    body: GroupCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    data = create_group(db, name=body.name, description=body.description)
    db.commit()
    log_operation(db, admin.id, "创建用户组", "group", data["id"], body.name)
    return data


@router.put("/{group_id}", response_model=GroupResponse)
def admin_update_group(
    group_id: int,
    body: GroupUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    payload = body.model_dump(exclude_unset=True)
    data = update_group(db, group_id, **payload)
    db.commit()
    log_operation(db, admin.id, "更新用户组", "group", group_id, data["name"])
    return data


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        delete_group(db, group_id)
    except GroupDeleteConflictError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.detail, "affected_acl_ids": exc.affected_acl_ids},
        )
    db.commit()
    log_operation(db, admin.id, "删除用户组", "group", group_id, "")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
