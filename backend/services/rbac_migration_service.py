# Copyright (c) 2026 徐泽宇
"""059 P3 T-22/T-23：workspace role 与 resource_grants → workspace_user_roles + batch folder_acl。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from models.enterprise_rbac import SUBJECT_ROLE, FolderAcl
from models.folder import Folder
from models.workspace import WORKSPACE_KIND_SHARED, Workspace, WorkspaceMember
from services.enterprise_rbac_seed import get_enterprise_role_by_slug
from services.folder_acl_admin_service import upsert_folder_acl_entry
from services.workspace_member_service import (
    LEGACY_WORKSPACE_ROLE_TO_ENTERPRISE_SLUG,
    sync_workspace_user_roles_from_legacy,
)

# legacy 映射后的企业角色 → 空间根 / 各目录 batch ACL（一次性迁移；新目录仍须单独配置）
_ROLE_BATCH_ACL: dict[str, dict[str, str | None]] = {
    "space_admin": {"root": "manage", "folder": "manage"},
    "folder_admin": {"root": None, "folder": "manage"},
    "editor": {"root": None, "folder": "write"},
    "viewer": {"root": None, "folder": "read"},
    "auditor": {"root": None, "folder": "read"},
}


@dataclass
class WorkspaceRoleMigrationReport:
    workspace_id: int
    workspace_name: str
    members_migrated: int = 0
    role_slugs_batch_applied: list[str] = field(default_factory=list)
    folder_acl_created: int = 0
    folder_acl_updated: int = 0
    root_acl_created: int = 0
    root_acl_updated: int = 0
    skipped: bool = False
    skip_reason: str | None = None


def _folder_ids_in_workspace(db: Session, workspace_id: int) -> list[int]:
    rows = db.query(Folder.id).filter(Folder.workspace_id == workspace_id).order_by(Folder.id).all()
    return [int(r[0]) for r in rows]


def _apply_role_batch_acl(
    db: Session,
    *,
    workspace_id: int,
    role_slug: str,
    folder_ids: list[int],
    actor_user_id: int,
    dry_run: bool = False,
) -> tuple[int, int, int, int]:
    """返回 (folder_created, folder_updated, root_created, root_updated)。"""
    spec = _ROLE_BATCH_ACL.get(role_slug)
    if not spec:
        return 0, 0, 0, 0

    role = get_enterprise_role_by_slug(db, role_slug)
    folder_created = folder_updated = root_created = root_updated = 0

    root_perm = spec.get("root")
    if root_perm:
        if dry_run:
            if count_role_folder_acl(
                db, workspace_id=workspace_id, role_slug=role_slug, folder_id=None
            ):
                root_updated += 1
            else:
                root_created += 1
        else:
            _, created = upsert_folder_acl_entry(
                db,
                workspace_id=workspace_id,
                folder_id=None,
                subject_type=SUBJECT_ROLE,
                subject_id=role.id,
                permission=root_perm,
                admin_user_id=actor_user_id,
            )
            if created:
                root_created += 1
            else:
                root_updated += 1

    folder_perm = spec.get("folder")
    if folder_perm:
        for folder_id in folder_ids:
            if dry_run:
                if count_role_folder_acl(
                    db,
                    workspace_id=workspace_id,
                    role_slug=role_slug,
                    folder_id=folder_id,
                ):
                    folder_updated += 1
                else:
                    folder_created += 1
            else:
                _, created = upsert_folder_acl_entry(
                    db,
                    workspace_id=workspace_id,
                    folder_id=folder_id,
                    subject_type=SUBJECT_ROLE,
                    subject_id=role.id,
                    permission=folder_perm,
                    admin_user_id=actor_user_id,
                )
                if created:
                    folder_created += 1
                else:
                    folder_updated += 1

    return folder_created, folder_updated, root_created, root_updated


def migrate_workspace_roles_for_workspace(
    db: Session,
    workspace: Workspace,
    *,
    actor_user_id: int,
    dry_run: bool = False,
) -> WorkspaceRoleMigrationReport:
    """单共享空间：成员 WUR 同步 + 按角色 batch folder_acl（幂等 upsert）。"""
    report = WorkspaceRoleMigrationReport(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
    )
    if workspace.kind != WORKSPACE_KIND_SHARED:
        report.skipped = True
        report.skip_reason = "not_shared"
        return report

    members = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace.id)
        .order_by(WorkspaceMember.user_id)
        .all()
    )
    role_slugs: set[str] = set()
    for member in members:
        slug = LEGACY_WORKSPACE_ROLE_TO_ENTERPRISE_SLUG.get(member.role)
        if not slug:
            continue
        if not dry_run:
            sync_workspace_user_roles_from_legacy(
                db,
                workspace_id=workspace.id,
                user_id=member.user_id,
                legacy_role=member.role,
            )
        report.members_migrated += 1
        if slug in _ROLE_BATCH_ACL:
            role_slugs.add(slug)

    folder_ids = _folder_ids_in_workspace(db, workspace.id)
    for slug in sorted(role_slugs):
        fc, fu, rc, ru = _apply_role_batch_acl(
            db,
            workspace_id=workspace.id,
            role_slug=slug,
            folder_ids=folder_ids,
            actor_user_id=actor_user_id,
            dry_run=dry_run,
        )
        report.folder_acl_created += fc
        report.folder_acl_updated += fu
        report.root_acl_created += rc
        report.root_acl_updated += ru

    report.role_slugs_batch_applied = sorted(role_slugs)
    return report


def migrate_workspace_roles(
    db: Session,
    *,
    workspace_id: int | None = None,
    dry_run: bool = False,
    actor_user_id: int,
) -> dict:
    """迁移全部（或指定）共享空间的 legacy 成员角色与 batch ACL。"""
    q = db.query(Workspace).filter(Workspace.kind == WORKSPACE_KIND_SHARED)
    if workspace_id is not None:
        q = q.filter(Workspace.id == workspace_id)
    workspaces = q.order_by(Workspace.id).all()

    reports: list[WorkspaceRoleMigrationReport] = []
    for ws in workspaces:
        reports.append(
            migrate_workspace_roles_for_workspace(
                db, ws, actor_user_id=actor_user_id, dry_run=dry_run
            )
        )
    if not dry_run:
        db.flush()

    summary = {
        "workspaces_processed": len(reports),
        "members_migrated": sum(r.members_migrated for r in reports),
        "folder_acl_created": sum(r.folder_acl_created for r in reports),
        "folder_acl_updated": sum(r.folder_acl_updated for r in reports),
        "root_acl_created": sum(r.root_acl_created for r in reports),
        "root_acl_updated": sum(r.root_acl_updated for r in reports),
    }
    return {
        "dry_run": dry_run,
        "summary": summary,
        "workspaces": [asdict(r) for r in reports],
    }


def count_workspace_user_roles(db: Session, *, workspace_id: int, user_id: int) -> int:
    from models.enterprise_rbac import WorkspaceUserRole

    return (
        db.query(WorkspaceUserRole)
        .filter(
            WorkspaceUserRole.workspace_id == workspace_id,
            WorkspaceUserRole.user_id == user_id,
        )
        .count()
    )


def count_role_folder_acl(
    db: Session,
    *,
    workspace_id: int,
    role_slug: str,
    folder_id: int | None,
) -> int:
    role = get_enterprise_role_by_slug(db, role_slug)
    q = db.query(FolderAcl).filter(
        FolderAcl.workspace_id == workspace_id,
        FolderAcl.subject_type == SUBJECT_ROLE,
        FolderAcl.subject_id == role.id,
    )
    if folder_id is None:
        q = q.filter(FolderAcl.folder_id.is_(None))
    else:
        q = q.filter(FolderAcl.folder_id == folder_id)
    return q.count()

# --- T-23: resource_grants → folder_acl ---

_LEGACY_GRANT_PERMISSION_MAP = {
    "view": "read",
    "edit": "write",
}


@dataclass
class WorkspaceResourceGrantMigrationReport:
    workspace_id: int
    workspace_name: str
    grants_processed: int = 0
    folder_grants_expanded: int = 0
    file_grants_to_folder: int = 0
    file_grants_shim_retained: int = 0
    orphan_grants_skipped: int = 0
    folder_acl_created: int = 0
    folder_acl_updated: int = 0
    warnings: list[dict] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None


def _map_grant_permission(legacy_perm: str) -> str:
    mapped = _LEGACY_GRANT_PERMISSION_MAP.get(legacy_perm)
    if not mapped:
        raise ValueError(f"未知 resource_grants.permission: {legacy_perm}")
    return mapped


def _upsert_user_folder_acl(
    db: Session,
    *,
    workspace_id: int,
    folder_id: int | None,
    user_id: int,
    permission: str,
    actor_user_id: int,
    dry_run: bool = False,
) -> tuple[bool, bool]:
    """返回 (created, updated)。"""
    from models.enterprise_rbac import PERMISSION_RANK, SUBJECT_USER
    from services.folder_acl_admin_service import _find_acl_row, upsert_folder_acl_entry

    if dry_run:
        existing = _find_acl_row(
            db,
            workspace_id=workspace_id,
            folder_id=folder_id,
            subject_type=SUBJECT_USER,
            subject_id=user_id,
        )
        return (0, 1) if existing else (1, 0)

    existing = _find_acl_row(
        db,
        workspace_id=workspace_id,
        folder_id=folder_id,
        subject_type=SUBJECT_USER,
        subject_id=user_id,
    )
    effective = permission
    if existing and PERMISSION_RANK.get(existing.permission, 0) > PERMISSION_RANK.get(permission, 0):
        effective = existing.permission
    _, created = upsert_folder_acl_entry(
        db,
        workspace_id=workspace_id,
        folder_id=folder_id,
        subject_type=SUBJECT_USER,
        subject_id=user_id,
        permission=effective,
        admin_user_id=actor_user_id,
    )
    return (created, not created)


def migrate_resource_grants_for_workspace(
    db: Session,
    workspace: Workspace,
    *,
    actor_user_id: int,
    dry_run: bool = False,
) -> WorkspaceResourceGrantMigrationReport:
    from models.file import File as FileModel
    from models.resource_grant import RESOURCE_FILE, RESOURCE_FOLDER, ResourceGrant
    from services.folder_tree_service import collect_descendant_folder_ids

    report = WorkspaceResourceGrantMigrationReport(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
    )
    if workspace.kind != WORKSPACE_KIND_SHARED:
        report.skipped = True
        report.skip_reason = "not_shared"
        return report

    grants = (
        db.query(ResourceGrant)
        .filter(ResourceGrant.workspace_id == workspace.id)
        .order_by(ResourceGrant.id)
        .all()
    )

    for grant in grants:
        report.grants_processed += 1
        permission = _map_grant_permission(grant.permission)

        if grant.resource_type == RESOURCE_FOLDER:
            folder = (
                db.query(Folder)
                .filter(Folder.id == grant.resource_id, Folder.workspace_id == workspace.id)
                .first()
            )
            if not folder:
                report.orphan_grants_skipped += 1
                report.warnings.append(
                    {
                        "grant_id": grant.id,
                        "code": "orphan_grant",
                        "message": "folder 已不存在，跳过迁移",
                        "workspace_id": workspace.id,
                        "resource_type": RESOURCE_FOLDER,
                        "resource_id": grant.resource_id,
                        "grantee_user_id": grant.grantee_user_id,
                    }
                )
                continue

            target_folder_ids = collect_descendant_folder_ids(
                db, int(grant.resource_id), workspace.id, include_root=True
            )
            report.folder_grants_expanded += 1
            for folder_id in target_folder_ids:
                created, updated = _upsert_user_folder_acl(
                    db,
                    workspace_id=workspace.id,
                    folder_id=folder_id,
                    user_id=grant.grantee_user_id,
                    permission=permission,
                    actor_user_id=actor_user_id,
                    dry_run=dry_run,
                )
                if created:
                    report.folder_acl_created += 1
                elif updated:
                    report.folder_acl_updated += 1
            continue

        if grant.resource_type == RESOURCE_FILE:
            file_row = (
                db.query(FileModel)
                .filter(FileModel.id == grant.resource_id, FileModel.workspace_id == workspace.id)
                .first()
            )
            if not file_row:
                report.orphan_grants_skipped += 1
                report.warnings.append(
                    {
                        "grant_id": grant.id,
                        "code": "orphan_grant",
                        "message": "file 已不存在，跳过迁移",
                        "workspace_id": workspace.id,
                        "resource_type": RESOURCE_FILE,
                        "resource_id": grant.resource_id,
                        "grantee_user_id": grant.grantee_user_id,
                    }
                )
                continue

            if file_row.folder_id is None:
                report.file_grants_shim_retained += 1
                report.warnings.append(
                    {
                        "grant_id": grant.id,
                        "code": "file_no_folder_shim",
                        "message": "未分类 file grant 保留在 resource_grants shim，需人工处理",
                        "workspace_id": workspace.id,
                        "file_id": file_row.id,
                        "grantee_user_id": grant.grantee_user_id,
                    }
                )
                continue

            parent_folder = (
                db.query(Folder)
                .filter(Folder.id == file_row.folder_id, Folder.workspace_id == workspace.id)
                .first()
            )
            if not parent_folder:
                report.orphan_grants_skipped += 1
                report.warnings.append(
                    {
                        "grant_id": grant.id,
                        "code": "orphan_grant",
                        "message": "file 父目录已不存在，跳过迁移",
                        "workspace_id": workspace.id,
                        "resource_type": RESOURCE_FILE,
                        "resource_id": grant.resource_id,
                        "grantee_user_id": grant.grantee_user_id,
                    }
                )
                continue

            report.file_grants_to_folder += 1
            created, updated = _upsert_user_folder_acl(
                db,
                workspace_id=workspace.id,
                folder_id=int(file_row.folder_id),
                user_id=grant.grantee_user_id,
                permission=permission,
                actor_user_id=actor_user_id,
                dry_run=dry_run,
            )
            if created:
                report.folder_acl_created += 1
            elif updated:
                report.folder_acl_updated += 1
            report.warnings.append(
                {
                    "grant_id": grant.id,
                    "code": "file_parent_over_grant",
                    "message": "file grant 已写入父目录 user ACL，可能 over-grant 兄弟文件",
                    "workspace_id": workspace.id,
                    "file_id": file_row.id,
                    "folder_id": int(file_row.folder_id),
                    "grantee_user_id": grant.grantee_user_id,
                }
            )

    return report


def migrate_resource_grants(
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

    reports: list[WorkspaceResourceGrantMigrationReport] = []
    for ws in workspaces:
        reports.append(
            migrate_resource_grants_for_workspace(
                db, ws, actor_user_id=actor_user_id, dry_run=dry_run
            )
        )
    if not dry_run:
        db.flush()

    summary = {
        "workspaces_processed": len(reports),
        "grants_processed": sum(r.grants_processed for r in reports),
        "folder_grants_expanded": sum(r.folder_grants_expanded for r in reports),
        "file_grants_to_folder": sum(r.file_grants_to_folder for r in reports),
        "file_grants_shim_retained": sum(r.file_grants_shim_retained for r in reports),
        "orphan_grants_skipped": sum(r.orphan_grants_skipped for r in reports),
        "folder_acl_created": sum(r.folder_acl_created for r in reports),
        "folder_acl_updated": sum(r.folder_acl_updated for r in reports),
        "warnings_count": sum(len(r.warnings) for r in reports),
    }
    return {
        "dry_run": dry_run,
        "summary": summary,
        "workspaces": [asdict(r) for r in reports],
    }


def count_user_folder_acl(
    db: Session,
    *,
    workspace_id: int,
    user_id: int,
    folder_id: int,
    permission: str | None = None,
) -> int:
    from models.enterprise_rbac import SUBJECT_USER

    q = db.query(FolderAcl).filter(
        FolderAcl.workspace_id == workspace_id,
        FolderAcl.folder_id == folder_id,
        FolderAcl.subject_type == SUBJECT_USER,
        FolderAcl.subject_id == user_id,
    )
    if permission is not None:
        q = q.filter(FolderAcl.permission == permission)
    return q.count()

