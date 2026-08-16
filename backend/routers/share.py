# Copyright (c) 2026 徐泽宇
"""share HTTP 路由模块。

Authors:
    徐泽宇
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.user import User
from schemas.share import CreateShareRequest, CreateShareResponse, ShareInfoResponse, VerifyPasswordRequest
from services.share_service import (
    create_share_link,
    get_share_by_token,
    increment_download,
    is_share_download_verified,
    set_share_download_cookie,
    verify_share_password,
    SHARE_VERIFY_COOKIE,
)
from services.log_service import log_operation
from utils.timezone import to_beijing_time

router = APIRouter()


def _reject_password_query(password: str | None) -> None:
    if password is not None and str(password).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请勿在 URL 查询参数中传递密码；请先 POST /verify 或使用 POST /download",
        )


def _ensure_share_password(
    request: Request,
    token: str,
    share,
    *,
    body_password: str | None = None,
) -> None:
    if not share.password_hash:
        return
    cookie_val = request.cookies.get(SHARE_VERIFY_COOKIE)
    if is_share_download_verified(token, cookie_val):
        return
    pwd = (body_password or "").strip()
    if not pwd:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要密码")
    if not verify_share_password(share, pwd):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")


def _share_file_response(db: Session, share) -> FileResponse:
    from models.file import File
    from services.md_paths import resolve_upload_path

    file = db.query(File).filter(File.id == share.file_id).first()
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")
    stream_path = resolve_upload_path(file.file_path) or file.file_path
    if not stream_path or not os.path.exists(stream_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料已不存在")

    increment_download(db, share)
    log_operation(db, share.created_by, "分享下载", "share", share.id, f"分享文件被下载: {file.original_name}")

    return FileResponse(
        stream_path,
        filename=file.original_name,
        media_type=file.mime_type,
    )


@router.post("", response_model=CreateShareResponse)
def create_share(
    body: CreateShareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        share = create_share_link(
            db,
            body.file_id,
            current_user.id,
            body.expires_in_hours,
            body.password,
            body.max_downloads,
        )
        log_operation(db, current_user.id, "创建分享", "share", share.id, f"分享文件 ID:{body.file_id}")
        return CreateShareResponse(
            token=share.token,
            url=f"/api/share/{share.token}/download",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{token}", response_model=ShareInfoResponse)
def get_share_info(token: str, db: Session = Depends(get_db)):
    share = get_share_by_token(db, token)
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="链接无效或已过期")

    from models.file import File
    file = db.query(File).filter(File.id == share.file_id).first()
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资料不存在")

    return ShareInfoResponse(
        id=share.id,
        token=share.token,
        file_id=share.file_id,
        file_name=file.original_name,
        file_size=file.file_size,
        mime_type=file.mime_type,
        expires_at=to_beijing_time(share.expires_at).isoformat() if share.expires_at else None,
        has_password=share.password_hash is not None,
        max_downloads=share.max_downloads,
        download_count=share.download_count,
        created_at=to_beijing_time(share.created_at).isoformat() if share.created_at else "",
    )


@router.post("/{token}/verify")
def verify_password(
    token: str,
    body: VerifyPasswordRequest,
    db: Session = Depends(get_db),
):
    share = get_share_by_token(db, token)
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="链接无效或已过期")
    if not verify_share_password(share, body.password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")
    resp = JSONResponse(content={"message": "验证通过"})
    set_share_download_cookie(resp, token)
    return resp


@router.get("/{token}/download")
def download_shared_file_get(
    token: str,
    request: Request,
    password: str | None = None,
    db: Session = Depends(get_db),
):
    _reject_password_query(password)
    share = get_share_by_token(db, token)
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="链接无效或已过期")
    _ensure_share_password(request, token, share)
    return _share_file_response(db, share)


@router.post("/{token}/download")
def download_shared_file_post(
    token: str,
    request: Request,
    body: VerifyPasswordRequest | None = None,
    db: Session = Depends(get_db),
):
    share = get_share_by_token(db, token)
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="链接无效或已过期")
    body_password = body.password if body else None
    _ensure_share_password(request, token, share, body_password=body_password)
    resp = _share_file_response(db, share)
    if share.password_hash and body_password:
        set_share_download_cookie(resp, token)
    return resp
