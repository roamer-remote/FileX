# Copyright (c) 2026 徐泽宇
"""059 P2 T-12：管理员部门 CRUD。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_admin_user
from models.user import User
from schemas.admin_rbac import (
    DepartmentCreateRequest,
    DepartmentResponse,
    DepartmentUpdateRequest,
)
from services.department_service import (
    DepartmentDeleteConflictError,
    create_department,
    delete_department,
    list_departments,
    update_department,
)
from services.log_service import log_operation

router = APIRouter()


@router.get("", response_model=list[DepartmentResponse])
def admin_list_departments(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return list_departments(db)


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def admin_create_department(
    body: DepartmentCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    data = create_department(db, name=body.name, parent_id=body.parent_id, sort_order=body.sort_order)
    db.commit()
    log_operation(db, admin.id, "创建部门", "department", data["id"], body.name)
    return data


@router.put("/{department_id}", response_model=DepartmentResponse)
def admin_update_department(
    department_id: int,
    body: DepartmentUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    payload = body.model_dump(exclude_unset=True)
    data = update_department(db, department_id, **payload)
    db.commit()
    log_operation(db, admin.id, "更新部门", "department", department_id, data["name"])
    return data


@router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_department(
    department_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        delete_department(db, department_id)
    except DepartmentDeleteConflictError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.detail, "affected_acl_ids": exc.affected_acl_ids},
        )
    db.commit()
    log_operation(db, admin.id, "删除部门", "department", department_id, "")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
