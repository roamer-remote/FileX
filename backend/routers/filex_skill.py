# Copyright (c) 2026 徐泽宇
"""filex_skill HTTP 路由模块。

Authors:
    徐泽宇
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.user import User
from services import skill_repository as repo
from services import skill_runtime_service as runtime
from utils.pubmed_skill import API_REF_MODULE_ID

router = APIRouter()


def _not_ready():
    return JSONResponse(
        status_code=503,
        content={"detail": "FileX 技能数据未初始化：请从磁盘同步 skill/ding。"},
    )


def _markdown_response(
    content: bytes,
    etag: str,
    skill_version: str,
    if_none_match: str | None,
    extra_headers: dict | None = None,
) -> Response:
    headers = {
        "ETag": etag,
        "X-Skill-Version": skill_version,
        "Cache-Control": "private, max-age=300",
    }
    if extra_headers:
        headers.update(extra_headers)
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers=headers)
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )


@router.get("/manifest")
def filex_skill_manifest(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    if not runtime.data_ready(db):
        return _not_ready()
    manifest = runtime.get_manifest(db)
    if manifest is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "FileX 技能包不完整。"},
        )
    return JSONResponse(
        content=manifest,
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.get("/modules/{module_path:path}")
def filex_skill_module(
    module_path: str,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    if not runtime.data_ready(db):
        return _not_ready()
    fid = f"module:{module_path}"
    if repo.get_head(db, fid) is None:
        raise HTTPException(status_code=404, detail="未知的 skill module")
    result = runtime.read_module(db, module_path)
    if result is None:
        return JSONResponse(status_code=503, content={"detail": "FileX 技能模块不可用。"})
    content, etag, skill_version = result
    return _markdown_response(content, etag, skill_version, if_none_match)


@router.get("/references/filex-agent-api")
def filex_skill_api_reference(
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    if not runtime.data_ready(db):
        return _not_ready()
    result = runtime.read_module(db, API_REF_MODULE_ID)
    if result is None:
        return JSONResponse(status_code=503, content={"detail": "FileX API 参考不可用。"})
    content, etag, skill_version = result
    manifest = runtime.get_manifest(db)
    api_ref_version = manifest.get("api_ref_version", "") if manifest else ""
    return _markdown_response(
        content, etag, skill_version, if_none_match,
        extra_headers={"X-Api-Ref-Version": api_ref_version} if api_ref_version else None,
    )
