# Copyright (c) 2026 徐泽宇
"""059 P3 T-26：S3 反向迁移 — folder_acl（legacy-mappable）与 WUR → 旧表。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.enterprise_rbac import EnterpriseRole, FolderAcl, WorkspaceUserRole
from models.resource_grant import RESOURCE_FOLDER, ResourceGrant
from models.workspace import WORKSPACE_KIND_SHARED, Workspace, WorkspaceMember
from services.acl_service import create_grant
from services.rbac_dual_write_service import ACL_TO_LEGACY_GRANT, is_legacy_mappable_folder_acl
from services.workspace_member_service import LEGACY_WORKSPACE_ROLE_TO_ENTERPRISE_SLUG

_ENTERPRISE_SLUG_TO_LEGACY = {v: k for k, v in LEGACY_WORKSPACE_ROLE_TO_ENTERPRISE_SLUG.items()}
_ROLE_PRIORITY = ("space_admin", "folder_admin", "editor", "auditor", "viewer")


def _pick_legacy_role(slugs: list[str]) -> str | None:
    for slug in _ROLE_PRIORITY:
        if slug in slugs:
            return _ENTERPRISE_SLUG_TO_LEGACY.get(slug)
    return None


def reverse_workspace_to_legacy(
    db: Session,
    workspace: Workspace,
    *,
    actor_user_id: int,
    dry_run: bool = False,
) -> dict:
    """单共享空间：WUR → workspace_members.role；legacy-mappable folder_acl → resource_grants。"""
    if workspace.kind != WORKSPACE_KIND_SHARED:
        return {
            "workspace_id": workspace.id,
            "skipped": True,
            "skip_reason": "not_shared",
        }

    members_synced = 0
    grants_mirrored = 0
    grants_updated = 0
    non_mappable_acl_skipped = 0
    warnings: list[dict] = []

    members = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace.id)
        .order_by(WorkspaceMember.user_id)
        .all()
    )
    for member in members:
        rows = (
            db.query(EnterpriseRole.slug)
            .join(WorkspaceUserRole, WorkspaceUserRole.role_id == EnterpriseRole.id)
            .filter(
                WorkspaceUserRole.workspace_id == workspace.id,
                WorkspaceUserRole.user_id == member.user_id,
            )
            .all()
        )
        slugs = [str(r[0]) for r in rows]
        if len(slugs) > 1:
            warnings.append(
                {
                    "code": "multi_role_reverse",
                    "message": "多企业角色成员反向迁移取最高权限 legacy role",
                    "user_id": member.user_id,
                    "slugs": slugs,
                }
            )
        legacy = _pick_legacy_role(slugs)
        if legacy and not dry_run:
            member.role = legacy
            members_synced += 1
        elif legacy:
            members_synced += 1

    acl_rows = (
        db.query(FolderAcl)
        .filter(FolderAcl.workspace_id == workspace.id)
        .order_by(FolderAcl.id)
        .all()
    )
    for row in acl_rows:
        if not is_legacy_mappable_folder_acl(
            folder_id=row.folder_id,
            subject_type=row.subject_type,
            permission=row.permission,
        ):
            non_mappable_acl_skipped += 1
            continue
        if dry_run:
            grants_mirrored += 1
            continue
        legacy_perm = ACL_TO_LEGACY_GRANT[row.permission]
        before = (
            db.query(ResourceGrant)
            .filter(
                ResourceGrant.workspace_id == workspace.id,
                ResourceGrant.resource_type == RESOURCE_FOLDER,
                ResourceGrant.resource_id == row.folder_id,
                ResourceGrant.grantee_user_id == row.subject_id,
            )
            .first()
        )
        create_grant(
            db,
            workspace_id=workspace.id,
            resource_type=RESOURCE_FOLDER,
            resource_id=int(row.folder_id),
            grantee_user_id=int(row.subject_id),
            permission=legacy_perm,
            created_by_user_id=actor_user_id,
            _internal_dual_write=True,
        )
        if before:
            grants_updated += 1
        else:
            grants_mirrored += 1

    if not dry_run:
        db.flush()

    return {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "members_synced": members_synced,
        "grants_mirrored": grants_mirrored,
        "grants_updated": grants_updated,
        "non_mappable_acl_skipped": non_mappable_acl_skipped,
        "warnings": warnings,
    }


def reverse_to_legacy(
    db: Session,
    *,
    workspace_id: int | None = None,
    dry_run: bool = False,
    actor_user_id: int,
) -> dict:
    q = db.query(Workspace).filter(Workspace.kind == WORKSPACE_KIND_SHARED)
    if workspace_id is not None:
        q = q.filter(Workspace.id == workspace_id)
    workspaces = q.order_by(Workspace.id).all()

    reports = [
        reverse_workspace_to_legacy(
            db, ws, actor_user_id=actor_user_id, dry_run=dry_run
        )
        for ws in workspaces
    ]
    return {
        "dry_run": dry_run,
        "workspaces_processed": len(reports),
        "summary": {
            "members_synced": sum(r.get("members_synced", 0) for r in reports),
            "grants_mirrored": sum(r.get("grants_mirrored", 0) for r in reports),
            "grants_updated": sum(r.get("grants_updated", 0) for r in reports),
            "non_mappable_acl_skipped": sum(
                r.get("non_mappable_acl_skipped", 0) for r in reports
            ),
        },
        "workspaces": reports,
    }
