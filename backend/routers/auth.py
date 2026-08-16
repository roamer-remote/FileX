# Copyright (c) 2026 徐泽宇
"""auth HTTP 路由模块。

Authors:
    徐泽宇
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse, ChangePasswordRequest
from services.auth_service import authenticate_user, create_access_token, change_password, create_user, record_user_login
from services.license_service import LicenseError, assert_license_valid, license_http_body
from services.avatar_service import validate_avatar_image
from services.log_service import log_operation
from middleware.auth import get_current_user
from models.user import User
from utils.rate_limit import (
    AUTH_LOGIN_RATE_LIMITER,
    AUTH_REGISTER_RATE_LIMITER,
    IpRateLimiter,
)
from utils.timezone import to_beijing_time

router = APIRouter()

logger = logging.getLogger("filex.auth")

_REGISTER_FIRST_USER_LOCK_KEY = 0x66696C65780001  # filex::register-first-user


def reset_auth_rate_limit_for_tests() -> None:
    """测试用：清空 login/register 限速计数。"""
    AUTH_LOGIN_RATE_LIMITER.reset_for_tests()
    AUTH_REGISTER_RATE_LIMITER.reset_for_tests()


@router.post("/change-password")
def change_password_endpoint(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        change_password(db, current_user, body.current_password, body.new_password)
        log_operation(db, current_user.id, "修改密码", "user", current_user.id, "用户修改登录密码")
        return {"message": "密码已更新"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    AUTH_LOGIN_RATE_LIMITER.check(IpRateLimiter.client_ip(request))
    logger.info("登录请求 username=%s", body.username)
    try:
        assert_license_valid(db)
    except LicenseError as e:
        return JSONResponse(status_code=403, content=license_http_body(e.status))
    try:
        user = authenticate_user(db, body.username, body.password)
        record_user_login(db, user)
        token = create_access_token(user.id, user.password_rev or 0)
        log_operation(db, user.id, "用户登录", "user", user.id, f"用户 {body.username} 登录")
        from services.workspace_service import ensure_personal_workspace
        ensure_personal_workspace(db, user)
        db.commit()
        logger.info("登录成功 user_id=%s username=%s", user.id, body.username)
        return TokenResponse(access_token=token)
    except ValueError as e:
        logger.warning("登录失败 username=%s detail=%s", body.username, e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    AUTH_REGISTER_RATE_LIMITER.check(IpRateLimiter.client_ip(request))
    try:
        assert_license_valid(db)
    except LicenseError as e:
        return JSONResponse(status_code=403, content=license_http_body(e.status))
    username = body.username.strip()
    if not username:
        logger.warning("注册拒绝：用户名为空")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名不能为空")
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": _REGISTER_FIRST_USER_LOCK_KEY},
    )
    is_first_user = db.query(User).count() == 0
    wechat_state = (body.wechat_state or "").strip() or None
    logger.info(
        "注册请求 username=%s first_user=%s wechat_state=%s",
        username,
        is_first_user,
        bool(wechat_state),
    )
    try:
        user = create_user(db, username, body.password, is_admin=is_first_user, commit=False)
        if wechat_state:
            from services.wechat_service import consume_state_for_register

            consume_state_for_register(db, wechat_state, user)
        record_user_login(db, user, commit=False)
        from services.workspace_service import ensure_personal_workspace

        ensure_personal_workspace(db, user)
        log_operation(db, user.id, "用户注册", "user", user.id, f"用户 {username} 公开注册")
        db.commit()
        db.refresh(user)
    except ValueError as e:
        db.rollback()
        logger.warning("注册失败 username=%s detail=%s", username, e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    token = create_access_token(user.id, user.password_rev or 0)
    logger.info("注册成功 user_id=%s username=%s is_admin=%s", user.id, username, user.is_admin)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        is_admin=current_user.is_admin,
        is_active=current_user.is_active,
        created_at=to_beijing_time(current_user.created_at).isoformat() if current_user.created_at else "",
        has_avatar=current_user.avatar_mime is not None,
        wechat_bound=current_user.wechat_openid is not None,
    )


@router.get("/avatar")
def get_my_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回当前用户数据库中的头像二进制；无头像时 404。"""
    u = db.query(User).filter(User.id == current_user.id).first()
    if not u or u.avatar_mime is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未上传头像")
    data = u.avatar_data
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未上传头像")
    return Response(
        content=data,
        media_type=u.avatar_mime,
        headers={"Cache-Control": "private, max-age=120"},
    )


@router.post("/avatar")
async def upload_my_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
):
    raw = await file.read()
    try:
        mime, data = validate_avatar_image(raw)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    u = db.query(User).filter(User.id == current_user.id).first()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    u.avatar_mime = mime
    u.avatar_data = data
    db.add(u)
    db.commit()
    log_operation(db, u.id, "更新头像", "user", u.id, "用户上传头像并写入数据库")
    return {"message": "头像已保存", "has_avatar": True}


@router.delete("/avatar")
def delete_my_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    u = db.query(User).filter(User.id == current_user.id).first()
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    u.avatar_mime = None
    u.avatar_data = None
    db.add(u)
    db.commit()
    log_operation(db, u.id, "删除头像", "user", u.id, "用户移除头像")
    return {"message": "头像已移除", "has_avatar": False}
