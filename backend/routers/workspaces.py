# Copyright (c) 2026 徐泽宇
"""workspaces HTTP 路由模块。

Authors:
    徐泽宇
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from database import get_db
from middleware.auth import get_admin_user, get_current_user
from models.kb_search_audit_log import KbSearchAuditLog
from models.resource_grant import ResourceGrant
from models.user import User
from models.workspace import Workspace, WorkspaceMember, WORKSPACE_KIND_SHARED
from schemas.workspace import (
    KbSearchAuditItem,
    ResourceGrantCreateRequest,
    ResourceGrantResponse,
    WorkspaceCreateRequest,
    WorkspaceMemberResponse,
    WorkspaceMemberUpsertRequest,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from services.acl_service import create_grant
from services.log_service import log_operation
from services.enterprise_rbac_phase_service import assert_legacy_resource_grants_api_allowed
from services.workspace_access_service import (
    can_manage_members,
    require_personal_workspace_owner,
    require_workspace_member,
    uses_enterprise_rbac_for_workspace,
)
from services.workspace_backup_service import (
    WorkspaceBackupTooLargeError,
    build_workspace_backup_zip,
)
from services.workspace_member_service import member_display_role, remove_workspace_member, upsert_workspace_member
from services.workspace_service import (
    create_shared_workspace,
    ensure_personal_workspace,
    list_user_workspaces,
)
from services.system_setting_service import is_shared_workspaces_enabled
from utils.timezone import to_beijing_time

router = APIRouter()


def _require_workspace_api_access(db: Session, workspace_id: int) -> Workspace:
    """共享库功能关闭时，阻断对共享空间元数据 API 的访问。"""
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识空间不存在")
    if ws.kind == WORKSPACE_KIND_SHARED and not is_shared_workspaces_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="共享知识空间功能未开启",
        )
    return ws


def _assert_can_manage_members(db: Session, user: User, workspace_id: int) -> None:
    if not can_manage_members(db, user, workspace_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权管理该知识空间成员",
        )


def _ws_response(ws: Workspace, role: str) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        kind=ws.kind,
        owner_user_id=ws.owner_user_id,
        my_role=role,
        created_at=to_beijing_time(ws.created_at).isoformat() if ws.created_at else "",
    )


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_personal_workspace(db, current_user)
    db.commit()
    rows = list_user_workspaces(db, current_user.id)
    if not is_shared_workspaces_enabled(db):
        rows = [(ws, role) for ws, role in rows if ws.kind != WORKSPACE_KIND_SHARED]
    return [_ws_response(ws, role) for ws, role in rows]


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可创建共享知识空间",
        )
    if not is_shared_workspaces_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="共享知识空间功能未开启",
        )
    ws = create_shared_workspace(db, name=body.name, owner=current_user)
    db.commit()
    db.refresh(ws)
    log_operation(db, current_user.id, "创建知识空间", "workspace", ws.id, body.name)
    return _ws_response(ws, "admin")


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = _require_workspace_api_access(db, workspace_id)
    member = require_workspace_member(db, current_user, workspace_id)
    return _ws_response(ws, member.role)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: int,
    body: WorkspaceUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = _require_workspace_api_access(db, workspace_id)
    member = require_workspace_member(db, current_user, workspace_id, minimum="admin")
    if ws.kind == "personal":
        raise HTTPException(status_code=400, detail="个人库不可重命名")
    ws.name = body.name.strip()
    db.commit()
    db.refresh(ws)
    return _ws_response(ws, member.role)


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberResponse])
def list_members(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workspace_api_access(db, workspace_id)
    _assert_can_manage_members(db, current_user, workspace_id)
    rbac_on = uses_enterprise_rbac_for_workspace(db, workspace_id)
    rows = (
        db.query(WorkspaceMember, User.username)
        .join(User, User.id == WorkspaceMember.user_id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .all()
    )
    return [
        WorkspaceMemberResponse(
            user_id=m.user_id,
            username=uname,
            role=member_display_role(
                db,
                workspace_id=workspace_id,
                user_id=m.user_id,
                legacy_role=m.role,
                rbac_on=rbac_on,
            ),
        )
        for m, uname in rows
    ]


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberResponse)
def upsert_member(
    workspace_id: int,
    body: WorkspaceMemberUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workspace_api_access(db, workspace_id)
    _assert_can_manage_members(db, current_user, workspace_id)
    target = db.query(User).filter(User.id == body.user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    m = upsert_workspace_member(
        db,
        workspace_id=workspace_id,
        target_user_id=body.user_id,
        legacy_role=body.role,
        acting_user=current_user,
    )
    db.commit()
    rbac_on = uses_enterprise_rbac_for_workspace(db, workspace_id)
    display_role = member_display_role(
        db,
        workspace_id=workspace_id,
        user_id=m.user_id,
        legacy_role=m.role,
        rbac_on=rbac_on,
    )
    return WorkspaceMemberResponse(user_id=m.user_id, username=target.username, role=display_role)


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    workspace_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = _require_workspace_api_access(db, workspace_id)
    _assert_can_manage_members(db, current_user, workspace_id)
    if ws and ws.kind == "personal":
        raise HTTPException(status_code=400, detail="个人库不可移除成员")
    remove_workspace_member(db, workspace_id=workspace_id, user_id=user_id)
    db.commit()


@router.get("/{workspace_id}/grants", response_model=list[ResourceGrantResponse])
def list_grants(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assert_legacy_resource_grants_api_allowed(db)
    _require_workspace_api_access(db, workspace_id)
    require_workspace_member(db, current_user, workspace_id, minimum="curator")
    rows = (
        db.query(ResourceGrant, User.username)
        .join(User, User.id == ResourceGrant.grantee_user_id)
        .filter(ResourceGrant.workspace_id == workspace_id)
        .order_by(ResourceGrant.id.desc())
        .all()
    )
    return [
        ResourceGrantResponse(
            id=g.id,
            resource_type=g.resource_type,
            resource_id=g.resource_id,
            grantee_user_id=g.grantee_user_id,
            grantee_username=uname,
            permission=g.permission,
            created_at=to_beijing_time(g.created_at).isoformat() if g.created_at else "",
        )
        for g, uname in rows
    ]


@router.post("/{workspace_id}/grants", response_model=ResourceGrantResponse, status_code=201)
def add_grant(
    workspace_id: int,
    body: ResourceGrantCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assert_legacy_resource_grants_api_allowed(db)
    _require_workspace_api_access(db, workspace_id)
    require_workspace_member(db, current_user, workspace_id, minimum="curator")
    try:
        g = create_grant(
            db,
            workspace_id=workspace_id,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            grantee_user_id=body.grantee_user_id,
            permission=body.permission,
            created_by_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    uname = db.query(User.username).filter(User.id == g.grantee_user_id).scalar() or ""
    return ResourceGrantResponse(
        id=g.id,
        resource_type=g.resource_type,
        resource_id=g.resource_id,
        grantee_user_id=g.grantee_user_id,
        grantee_username=uname,
        permission=g.permission,
        created_at=to_beijing_time(g.created_at).isoformat() if g.created_at else "",
    )


@router.delete("/{workspace_id}/grants/{grant_id}", status_code=204)
def delete_grant(
    workspace_id: int,
    grant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assert_legacy_resource_grants_api_allowed(db)
    _require_workspace_api_access(db, workspace_id)
    require_workspace_member(db, current_user, workspace_id, minimum="curator")
    db.query(ResourceGrant).filter(
        ResourceGrant.id == grant_id,
        ResourceGrant.workspace_id == workspace_id,
    ).delete()
    db.commit()


def _unlink_temp_file(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


@router.get("/{workspace_id}/backup")
def download_workspace_backup(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = require_personal_workspace_owner(db, current_user, workspace_id)
    try:
        result = build_workspace_backup_zip(db, current_user, ws)
    except WorkspaceBackupTooLargeError as exc:
        http_413 = getattr(
            status,
            "HTTP_413_CONTENT_TOO_LARGE",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
        raise HTTPException(
            status_code=http_413,
            detail={
                "code": exc.detail,
                "total_bytes": exc.total_bytes,
                "max_bytes": exc.max_bytes,
                "file_count": exc.file_count,
            },
        ) from exc
    log_operation(
        db,
        current_user.id,
        "备份下载",
        "workspace",
        workspace_id,
        f"slug={ws.slug} files={result.file_count} bytes={result.total_bytes}",
    )
    db.commit()
    return FileResponse(
        result.zip_path,
        media_type="application/zip",
        filename=result.filename,
        background=BackgroundTask(_unlink_temp_file, result.zip_path),
    )


@router.get("/{workspace_id}/audit/search", response_model=list[KbSearchAuditItem])
def list_search_audit(
    workspace_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_workspace_api_access(db, workspace_id)
    require_workspace_member(db, current_user, workspace_id, minimum="auditor")
    rows = (
        db.query(KbSearchAuditLog, User.username)
        .join(User, User.id == KbSearchAuditLog.user_id)
        .filter(KbSearchAuditLog.workspace_id == workspace_id)
        .order_by(KbSearchAuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return [
        KbSearchAuditItem(
            id=log.id,
            user_id=log.user_id,
            username=uname,
            workspace_id=log.workspace_id,
            query=log.query,
            hit_file_ids=log.hit_file_ids,
            top_k=log.top_k,
            created_at=to_beijing_time(log.created_at).isoformat() if log.created_at else "",
        )
        for log, uname in rows
    ]
