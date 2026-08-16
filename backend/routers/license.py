# Copyright (c) 2026 徐泽宇
"""License 状态、续期与管理端 API（021）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_admin_user
from models.user import User
from config import license_hmac_secret, license_hmac_secret_env
from schemas.license import (
    LicenseActivateRequest,
    LicenseAdminStatusResponse,
    LicenseAdminUpdateRequest,
    LicenseStatusResponse,
)
from services.auth_service import authenticate_user
from services.license_cache_service import get_cached_status, invalidate_license_cache, warm_license_cache
from services.license_service import (
    KEY_LICENSE_KEY,
    activate_license,
    get_license_status,
    mask_license_key,
)
from services.log_service import log_operation
from utils.rate_limit import IpRateLimiter, LICENSE_ACTIVATE_RATE_LIMITER
from utils.timezone import to_beijing_time

router = APIRouter()
admin_router = APIRouter()

logger = logging.getLogger("filex.license")


def _client_ip(request: Request) -> str:
    return IpRateLimiter.client_ip(request)


def _check_activate_rate_limit(ip: str) -> None:
    LICENSE_ACTIVATE_RATE_LIMITER.check(ip)


def reset_activate_rate_limit_for_tests() -> None:
    """测试用：清空 activate 限速计数。"""
    LICENSE_ACTIVATE_RATE_LIMITER.reset_for_tests()


def _audit_user_id(db: Session, username: str) -> int:
    user = db.query(User).filter(User.username == username).first()
    if user is not None:
        return user.id
    admin = (
        db.query(User)
        .filter(User.is_admin.is_(True), User.is_active.is_(True))
        .order_by(User.id)
        .first()
    )
    if admin is not None:
        return admin.id
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="无法记录审计日志")


def _read_raw_license_key(db: Session) -> str:
    from models.system_setting import SystemSetting

    row = db.query(SystemSetting).filter(SystemSetting.setting_key == KEY_LICENSE_KEY).first()
    return (row.value if row else "") or ""


def _status_response(db: Session) -> LicenseStatusResponse:
    status_obj = get_cached_status(db)
    masked = mask_license_key(_read_raw_license_key(db))
    exp = status_obj.expires_at
    if exp is not None:
        exp = to_beijing_time(exp)
    return LicenseStatusResponse(
        valid=status_obj.valid,
        reason=status_obj.reason,
        expires_at=exp,
        customer_id=status_obj.customer_id,
        days_remaining=status_obj.days_remaining,
        in_trial=status_obj.in_trial,
        license_key_masked=masked,
    )


def _admin_status_response(db: Session) -> LicenseAdminStatusResponse:
    base = _status_response(db)
    effective = license_hmac_secret() or None
    env_secret = license_hmac_secret_env() or None
    return LicenseAdminStatusResponse(
        **base.model_dump(),
        license_hmac_secret=env_secret,
        license_hmac_secret_effective=effective,
    )


@router.get("/status", response_model=LicenseStatusResponse)
def license_status(db: Session = Depends(get_db)):
    return _status_response(db)


@router.post("/activate", response_model=LicenseStatusResponse)
def license_activate(body: LicenseActivateRequest, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    _check_activate_rate_limit(ip)

    try:
        user = authenticate_user(db, body.admin_username, body.admin_password)
    except ValueError as e:
        log_operation(
            db,
            _audit_user_id(db, body.admin_username),
            "授权激活失败",
            "license",
            None,
            f"IP={ip} 管理员认证失败: {e}",
            commit=False,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e

    if not user.is_admin:
        log_operation(
            db,
            user.id,
            "授权激活失败",
            "license",
            None,
            f"IP={ip} 非管理员账号 {body.admin_username}",
            commit=False,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员账号")

    try:
        activate_license(db, body.license_key.strip(), commit=False)
    except ValueError as e:
        log_operation(
            db,
            user.id,
            "授权激活失败",
            "license",
            None,
            f"IP={ip} {e}",
            commit=False,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    invalidate_license_cache()
    warm_license_cache(db)
    log_operation(
        db,
        user.id,
        "更新授权",
        "license",
        None,
        f"IP={ip} customer={get_license_status(db).customer_id or '-'}",
        commit=False,
    )
    db.commit()
    logger.info("license_activated user_id=%s ip=%s", user.id, ip)
    return _status_response(db)


@admin_router.get("", response_model=LicenseAdminStatusResponse)
def admin_get_license(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return _admin_status_response(db)


@admin_router.put("", response_model=LicenseAdminStatusResponse)
def admin_put_license(
    body: LicenseAdminUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    ip = _client_ip(request)
    try:
        activate_license(db, body.license_key.strip(), commit=False)
    except ValueError as e:
        log_operation(
            db,
            admin.id,
            "授权更新失败",
            "license",
            None,
            f"IP={ip} {e}",
            commit=False,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    invalidate_license_cache()
    warm_license_cache(db)
    log_operation(
        db,
        admin.id,
        "更新授权",
        "license",
        None,
        f"IP={ip} admin PUT customer={get_license_status(db).customer_id or '-'}",
        commit=False,
    )
    db.commit()
    return _admin_status_response(db)
