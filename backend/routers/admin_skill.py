# Copyright (c) 2026 徐泽宇
"""admin_skill HTTP 路由模块。

Authors:
    徐泽宇
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_admin_user
from models.user import User
from schemas.admin_skill import (
    AdminSkillSyncFromDiskResponse,
    AdminSkillFileResponse,
    AdminSkillFilesListResponse,
    AdminSkillFileItem,
)
from services import skill_cache_service as cache
from services import skill_repository as repo
from services.log_service import log_operation
from utils.pubmed_skill import is_managed_skill_file_id

router = APIRouter()


def _not_ready():
    return JSONResponse(
        status_code=503,
        content={"detail": "FileX 技能数据未初始化：请从磁盘同步 skill/ding。"},
    )


@router.get("/files", response_model=AdminSkillFilesListResponse)
def list_skill_files(db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    disk_skill_version = repo.read_disk_skill_version()
    if not repo.is_data_ready(db):
        return AdminSkillFilesListResponse(
            writable=False,
            data_ready=False,
            cache_enabled=cache.enabled(),
            skill_version=None,
            disk_skill_version=disk_skill_version,
            bootstrap_min_version=None,
            files=[],
        )
    files = repo.list_heads(db)
    if files is None:
        return JSONResponse(status_code=503, content={"detail": "FileX 技能包不完整。"})
    manifest = repo.build_manifest_dict(db)
    return AdminSkillFilesListResponse(
        writable=False,
        data_ready=True,
        cache_enabled=cache.enabled(),
        skill_version=manifest["skill_version"] if manifest else None,
        disk_skill_version=disk_skill_version,
        bootstrap_min_version=manifest["bootstrap_min_version"] if manifest else None,
        files=[AdminSkillFileItem(**f) for f in files],
    )


@router.get("/files/{file_id:path}", response_model=AdminSkillFileResponse)
def get_skill_file(file_id: str, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    if not is_managed_skill_file_id(file_id):
        raise HTTPException(status_code=404, detail="未知的 skill 文件")
    if not repo.is_data_ready(db):
        return _not_ready()
    data = repo.get_head_dict(db, file_id)
    if data is None:
        raise HTTPException(status_code=404, detail="skill 文件不存在")
    return AdminSkillFileResponse(**data)


@router.post("/sync-from-disk", response_model=AdminSkillSyncFromDiskResponse)
def sync_skill_from_disk(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Mirror skill/ding on disk into PostgreSQL (overwrite; disk is source of truth)."""
    result = repo.replace_all_from_disk(db, admin.id)
    if result.get("data_ready"):
        cache.warm_all(db)
    log_operation(
        db,
        admin.id,
        action="skill_sync_from_disk",
        target_type="skill",
        detail=(
            f"added={result.get('added')} updated={result.get('updated')} "
            f"removed={result.get('removed')}"
        ),
    )
    db.commit()
    return AdminSkillSyncFromDiskResponse(
        ok=bool(result.get("ok")),
        data_ready=bool(result.get("data_ready")),
        skill_dir=result.get("skill_dir"),
        synced=list(result.get("synced") or []),
        added=list(result.get("added") or []),
        updated=list(result.get("updated") or []),
        removed=list(result.get("removed") or []),
        reason=result.get("reason"),
    )
