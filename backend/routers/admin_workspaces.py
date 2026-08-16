# Copyright (c) 2026 徐泽宇
"""管理员专用：全站知识空间维护（仅 is_admin）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_admin_user
from models.kb_search_audit_log import KbSearchAuditLog
from models.resource_grant import ResourceGrant
from models.user import User
from models.workspace import WORKSPACE_KIND_SHARED, WORKSPACE_ROLES, Workspace, WorkspaceMember
from schemas.workspace import (
    AdminWorkspaceCreateRequest,
    AdminWorkspaceListItem,
    KbSearchAuditItem,
    ResourceGrantCreateRequest,
    ResourceGrantResponse,
    WorkspaceMemberResponse,
    WorkspaceMemberUpsertRequest,
    WorkspaceUpdateRequest,
)
from schemas.admin_rbac import (
    FolderAclBulkPutRequest,
    FolderAclEntryResponse,
    FolderAclFolderPutRequest,
    FolderAclPutSummaryResponse,
    WorkspaceMemberRolesResponse,
    WorkspaceMemberRolesUpdateRequest,
)
from services.acl_service import create_grant
from services.folder_acl_admin_service import (
    list_workspace_folder_acl,
    put_single_folder_acl,
    put_workspace_folder_acl_bulk,
    require_shared_workspace_for_acl,
    resolve_folder_id_for_workspace,
)
from services.log_service import log_operation
from services.system_setting_service import is_shared_workspaces_enabled
from services.enterprise_rbac_phase_service import assert_legacy_resource_grants_api_allowed
from services.workspace_member_roles_service import get_workspace_member_roles, set_workspace_member_roles
from services.workspace_member_service import remove_workspace_member, upsert_workspace_member
from services.workspace_service import create_shared_workspace, list_all_workspaces
from utils.timezone import to_beijing_time

router = APIRouter()


def _get_workspace_or_404(db: Session, workspace_id: int) -> Workspace:
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识空间不存在")
    if ws.kind == WORKSPACE_KIND_SHARED and not is_shared_workspaces_enabled(db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="共享知识空间功能未开启")
    return ws


@router.get("", response_model=list[AdminWorkspaceListItem])
def admin_list_workspaces(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    rows = list_all_workspaces(db)
    if not is_shared_workspaces_enabled(db):
        rows = [(ws, owner_name, count) for ws, owner_name, count in rows if ws.kind != WORKSPACE_KIND_SHARED]
    return [
        AdminWorkspaceListItem(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            kind=ws.kind,
            owner_user_id=ws.owner_user_id,
            owner_username=owner_name,
            member_count=count,
            created_at=to_beijing_time(ws.created_at).isoformat() if ws.created_at else "",
        )
        for ws, owner_name, count in rows
    ]


@router.post("", response_model=AdminWorkspaceListItem, status_code=status.HTTP_201_CREATED)
def admin_create_workspace(
    body: AdminWorkspaceCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    if not is_shared_workspaces_enabled(db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="共享知识空间功能未开启")
    owner = db.query(User).filter(User.id == body.owner_user_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="所有者用户不存在")
    ws = create_shared_workspace(db, name=body.name, owner=owner)
    db.commit()
    db.refresh(ws)
    log_operation(db, admin.id, "管理员创建知识空间", "workspace", ws.id, body.name)
    count = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == ws.id).count()
    return AdminWorkspaceListItem(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        kind=ws.kind,
        owner_user_id=ws.owner_user_id,
        owner_username=owner.username,
        member_count=count,
        created_at=to_beijing_time(ws.created_at).isoformat() if ws.created_at else "",
    )


@router.put("/{workspace_id}", response_model=AdminWorkspaceListItem)
def admin_update_workspace(
    workspace_id: int,
    body: WorkspaceUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    ws = _get_workspace_or_404(db, workspace_id)
    ws.name = body.name.strip()
    db.commit()
    db.refresh(ws)
    log_operation(db, admin.id, "管理员重命名知识空间", "workspace", ws.id, ws.name)
    owner_name = None
    if ws.owner_user_id:
        owner_name = db.query(User.username).filter(User.id == ws.owner_user_id).scalar()
    count = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == ws.id).count()
    return AdminWorkspaceListItem(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        kind=ws.kind,
        owner_user_id=ws.owner_user_id,
        owner_username=owner_name,
        member_count=count,
        created_at=to_beijing_time(ws.created_at).isoformat() if ws.created_at else "",
    )


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    ws = _get_workspace_or_404(db, workspace_id)
    if ws.kind != WORKSPACE_KIND_SHARED:
        raise HTTPException(status_code=400, detail="仅可删除共享知识空间")
    name = ws.name
    db.delete(ws)
    db.commit()
    log_operation(db, admin.id, "管理员删除知识空间", "workspace", workspace_id, name)


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberResponse])
def admin_list_members(
    workspace_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    _get_workspace_or_404(db, workspace_id)
    rows = (
        db.query(WorkspaceMember, User.username)
        .join(User, User.id == WorkspaceMember.user_id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .all()
    )
    return [WorkspaceMemberResponse(user_id=m.user_id, username=uname, role=m.role) for m, uname in rows]


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberResponse)
def admin_upsert_member(
    workspace_id: int,
    body: WorkspaceMemberUpsertRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    _get_workspace_or_404(db, workspace_id)
    if body.role not in WORKSPACE_ROLES:
        raise HTTPException(status_code=400, detail="无效角色")
    target = db.query(User).filter(User.id == body.user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    m = upsert_workspace_member(
        db,
        workspace_id=workspace_id,
        target_user_id=body.user_id,
        legacy_role=body.role,
        acting_user=admin,
    )
    db.commit()
    log_operation(
        db,
        admin.id,
        "管理员设置空间成员",
        "workspace",
        workspace_id,
        f"{target.username}={body.role}",
    )
    return WorkspaceMemberResponse(user_id=m.user_id, username=target.username, role=m.role)


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_remove_member(
    workspace_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    ws = _get_workspace_or_404(db, workspace_id)
    if ws.kind == "personal" and ws.owner_user_id == user_id:
        raise HTTPException(status_code=400, detail="不可移除个人库所有者")
    remove_workspace_member(db, workspace_id=workspace_id, user_id=user_id)
    db.commit()


@router.get(
    "/{workspace_id}/members/{user_id}/roles",
    response_model=WorkspaceMemberRolesResponse,
)
def admin_get_member_roles(
    workspace_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    ws = _get_workspace_or_404(db, workspace_id)
    result = get_workspace_member_roles(db, workspace=ws, user_id=user_id)
    return WorkspaceMemberRolesResponse(**result)


@router.put(
    "/{workspace_id}/members/{user_id}/roles",
    response_model=WorkspaceMemberRolesResponse,
)
def admin_set_member_roles(
    workspace_id: int,
    user_id: int,
    body: WorkspaceMemberRolesUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    ws = _get_workspace_or_404(db, workspace_id)
    result = set_workspace_member_roles(
        db,
        workspace=ws,
        user_id=user_id,
        role_ids=body.role_ids,
    )
    db.commit()
    role_label = result["role_slugs"] if result["role_slugs"] else "（已清空）"
    log_operation(
        db,
        admin.id,
        "管理员设置空间成员企业角色",
        "workspace",
        workspace_id,
        f"user={user_id} roles={role_label}",
    )
    return WorkspaceMemberRolesResponse(**result)


@router.get("/{workspace_id}/folder-acl", response_model=list[FolderAclEntryResponse])
def admin_list_folder_acl(
    workspace_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    ws = _get_workspace_or_404(db, workspace_id)
    require_shared_workspace_for_acl(ws)
    return list_workspace_folder_acl(db, workspace_id)


@router.put("/{workspace_id}/folder-acl", response_model=FolderAclPutSummaryResponse)
def admin_put_folder_acl_bulk(
    workspace_id: int,
    body: FolderAclBulkPutRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    ws = _get_workspace_or_404(db, workspace_id)
    require_shared_workspace_for_acl(ws)
    entries = [entry.model_dump() for entry in body.entries]
    summary = put_workspace_folder_acl_bulk(
        db,
        workspace_id=workspace_id,
        entries=entries,
        admin_user_id=admin.id,
    )
    db.commit()
    log_operation(
        db,
        admin.id,
        "管理员批量更新目录 ACL",
        "workspace",
        workspace_id,
        f"upserted={summary['upserted']} updated={summary['updated']}",
    )
    return FolderAclPutSummaryResponse(**summary)


@router.put(
    "/{workspace_id}/folders/{folder_id_or_root}/acl",
    response_model=FolderAclPutSummaryResponse,
)
def admin_put_folder_acl_for_folder(
    workspace_id: int,
    folder_id_or_root: str,
    body: FolderAclFolderPutRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    ws = _get_workspace_or_404(db, workspace_id)
    require_shared_workspace_for_acl(ws)
    folder_id = resolve_folder_id_for_workspace(
        db,
        workspace_id=workspace_id,
        folder_id_or_root=folder_id_or_root,
    )
    entries = [entry.model_dump() for entry in body.entries]
    summary = put_single_folder_acl(
        db,
        workspace_id=workspace_id,
        folder_id=folder_id,
        entries=entries,
        admin_user_id=admin.id,
    )
    db.commit()
    log_operation(
        db,
        admin.id,
        "管理员更新单目录 ACL",
        "workspace",
        workspace_id,
        f"folder={folder_id_or_root} upserted={summary['upserted']} updated={summary['updated']}",
    )
    return FolderAclPutSummaryResponse(**summary)


@router.get("/{workspace_id}/grants", response_model=list[ResourceGrantResponse])
def admin_list_grants(
    workspace_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    assert_legacy_resource_grants_api_allowed(db)
    _get_workspace_or_404(db, workspace_id)
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
def admin_add_grant(
    workspace_id: int,
    body: ResourceGrantCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    assert_legacy_resource_grants_api_allowed(db)
    _get_workspace_or_404(db, workspace_id)
    try:
        g = create_grant(
            db,
            workspace_id=workspace_id,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            grantee_user_id=body.grantee_user_id,
            permission=body.permission,
            created_by_user_id=admin.id,
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
def admin_delete_grant(
    workspace_id: int,
    grant_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    assert_legacy_resource_grants_api_allowed(db)
    _get_workspace_or_404(db, workspace_id)
    db.query(ResourceGrant).filter(
        ResourceGrant.id == grant_id,
        ResourceGrant.workspace_id == workspace_id,
    ).delete()
    db.commit()


@router.get("/{workspace_id}/audit/search", response_model=list[KbSearchAuditItem])
def admin_list_search_audit(
    workspace_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    _get_workspace_or_404(db, workspace_id)
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


@router.get("/{workspace_id}/audit/search/export")
def admin_export_search_audit(
    workspace_id: int,
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    _get_workspace_or_404(db, workspace_id)
    rows = (
        db.query(KbSearchAuditLog, User.username)
        .join(User, User.id == KbSearchAuditLog.user_id)
        .filter(KbSearchAuditLog.workspace_id == workspace_id)
        .order_by(KbSearchAuditLog.id.desc())
        .limit(limit)
        .all()
    )
    lines = ["id\tuser\tworkspace_id\tquery\thits\ttop_k\tcreated_at"]
    for log, uname in rows:
        q = (log.query or "").replace("\t", " ")
        hits = (log.hit_file_ids or "").replace("\t", " ")
        lines.append(
            f"{log.id}\t{uname}\t{log.workspace_id}\t{q}\t{hits}\t{log.top_k}\t{log.created_at}"
        )
    return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")
