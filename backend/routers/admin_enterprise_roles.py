# Copyright (c) 2026 徐泽宇
"""059 P2 T-14：管理员企业角色 CRUD。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_admin_user
from models.user import User
from schemas.admin_rbac import (
    EnterpriseRoleCreateRequest,
    EnterpriseRoleDeleteResponse,
    EnterpriseRoleResponse,
    EnterpriseRoleUpdateRequest,
)
from services.enterprise_role_service import (
    create_enterprise_role,
    delete_enterprise_role,
    list_enterprise_roles,
    update_enterprise_role,
)
from services.log_service import log_operation

router = APIRouter()


@router.get("", response_model=list[EnterpriseRoleResponse])
def admin_list_enterprise_roles(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return list_enterprise_roles(db)


@router.post("", response_model=EnterpriseRoleResponse, status_code=status.HTTP_201_CREATED)
def admin_create_enterprise_role(
    body: EnterpriseRoleCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    data = create_enterprise_role(db, slug=body.slug, name=body.name, description=body.description)
    db.commit()
    log_operation(db, admin.id, "创建企业角色", "enterprise_role", data["id"], body.slug)
    return data


@router.put("/{role_id}", response_model=EnterpriseRoleResponse)
def admin_update_enterprise_role(
    role_id: int,
    body: EnterpriseRoleUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    payload = body.model_dump(exclude_unset=True)
    data = update_enterprise_role(db, role_id, **payload)
    db.commit()
    log_operation(db, admin.id, "更新企业角色", "enterprise_role", role_id, data["slug"])
    return data


@router.delete("/{role_id}", response_model=EnterpriseRoleDeleteResponse)
def admin_delete_enterprise_role(
    role_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    summary = delete_enterprise_role(db, role_id)
    db.commit()
    log_operation(
        db,
        admin.id,
        "删除企业角色",
        "enterprise_role",
        role_id,
        f"wur={summary['deleted_user_role_assignments']} acl={summary['deleted_acl_rows']}",
    )
    return summary
