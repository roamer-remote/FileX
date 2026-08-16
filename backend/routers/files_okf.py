# Copyright (c) 2026 徐泽宇
"""files_okf HTTP 路由模块：OKF 源码与元数据 API。

Authors:
    徐泽宇
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.user import User
from services.log_service import log_operation
from services.okf_note_service import (
    effective_okf_frontmatter,
    okf_concept_path_conflict_exists,
    read_okf_raw_for_file,
    update_okf_frontmatter_for_file,
)
from services.tag_service import replace_file_tags
from utils.agent_freshness import apply_agent_no_cache_headers

from . import files as _files_mod

router = APIRouter()


class OkfMetaUpdate(BaseModel):
    type: str | None = None
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    okf_concept_path: str | None = None


def _normalize_concept_path(value: str | None) -> str:
    return (value or "").strip().strip("/").replace("\\", "/")


@router.get("/{file_id}/okf")
def get_file_okf_raw(
    file_id: int,
    response: Response,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回完整 OKF Markdown raw（frontmatter + body）。"""
    apply_agent_no_cache_headers(response)
    f, _ws = _files_mod.require_workspace_file(db, file_id, current_user, workspace_id)
    if not f.has_md or not f.md_file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该资料没有 Markdown 笔记")
    raw = read_okf_raw_for_file(f)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Markdown 笔记已不存在")
    return PlainTextResponse(raw, media_type="text/markdown; charset=utf-8")


@router.get("/{file_id}/okf/meta")
def get_file_okf_meta(
    file_id: int,
    response: Response,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回 OKF frontmatter JSON 与 concept_path。"""
    apply_agent_no_cache_headers(response)
    f, _ws = _files_mod.require_workspace_file(db, file_id, current_user, workspace_id)
    if not f.has_md or not f.md_file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该资料没有 Markdown 笔记")
    frontmatter = effective_okf_frontmatter(f)
    return {
        "okf_concept_path": f.okf_concept_path,
        "okf_type": f.okf_type or frontmatter.get("type"),
        "frontmatter": frontmatter,
    }


@router.put("/{file_id}/okf/meta")
def put_file_okf_meta(
    file_id: int,
    body: OkfMetaUpdate,
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新 OKF frontmatter；校验 type 非空、concept_path 唯一，path 冲突返回 409。

    metadata-only 更新：保留 body，不改 md_content_hash，不新增 md version；tags 三向同步。
    """
    f, _ws = _files_mod.require_workspace_file(db, file_id, current_user, workspace_id, need_write=True)
    if not f.has_md or not f.md_file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该资料没有 Markdown 笔记")

    frontmatter = effective_okf_frontmatter(f)
    if body.type is not None:
        frontmatter["type"] = body.type.strip()
    if body.title is not None:
        frontmatter["title"] = body.title.strip()
    if body.description is not None:
        if body.description.strip():
            frontmatter["description"] = body.description.strip()
        else:
            frontmatter.pop("description", None)
    if body.tags is not None:
        frontmatter["tags"] = list(body.tags)

    okf_type = str(frontmatter.get("type") or "").strip()
    if not okf_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="okf type 不能为空")
    frontmatter["type"] = okf_type

    new_path = _normalize_concept_path(body.okf_concept_path) if body.okf_concept_path is not None else None
    if new_path is not None and new_path != (f.okf_concept_path or ""):
        if not new_path:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="okf_concept_path 不能为空")
        if okf_concept_path_conflict_exists(db, f, new_path):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="okf_concept_path 已被其他资料占用",
            )
        concept_path_arg: str | None = new_path
    else:
        concept_path_arg = None

    update_okf_frontmatter_for_file(f, frontmatter, concept_path=concept_path_arg, db=db)

    if body.tags is not None:
        replace_file_tags(db, current_user.id, f.id, list(body.tags))

    db.commit()
    db.refresh(f)

    log_operation(
        db, current_user.id, "更新 OKF 元数据", "file", f.id,
        f"更新文件 {f.original_name} 的 OKF 元数据",
    )

    return {
        "okf_concept_path": f.okf_concept_path,
        "okf_type": f.okf_type,
        "okf_metadata": f.okf_metadata,
        "frontmatter": effective_okf_frontmatter(f),
    }
