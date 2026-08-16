# Copyright (c) 2026 徐泽宇
"""admin_users HTTP 路由模块。

Authors:
    徐泽宇
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_admin_user
from models.user import User
from schemas.admin import AdminCreateUserRequest
from schemas.admin_rbac import AdminUserOrgResponse, AdminUserOrgUpdateRequest
from services.auth_service import create_user, admin_set_user_password
from services.user_org_service import get_user_org, update_user_org
from services.log_service import log_operation
from utils.timezone import beijing_now, to_beijing_time

router = APIRouter()


@router.get("/users")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    query = db.query(User).order_by(User.created_at.asc())
    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()
    start_of_today = beijing_now().replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    admin_count = db.query(User).filter(User.is_admin.is_(True)).count()
    active_today_count = db.query(User).filter(User.last_login_at >= start_of_today).count()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": {
            "admin_count": admin_count,
            "active_today_count": active_today_count,
        },
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "is_admin": u.is_admin,
                "is_active": u.is_active,
                "created_at": to_beijing_time(u.created_at).isoformat() if u.created_at else "",
                "last_login_at": to_beijing_time(u.last_login_at).isoformat() if u.last_login_at else "",
                "wechat_nickname": u.wechat_nickname or "",
                "wechat_openid": u.wechat_openid or "",
            }
            for u in users
        ],
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user_admin(
    body: AdminCreateUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        user = create_user(db, body.username, body.password, is_admin=body.is_admin)
        log_operation(db, admin.id, "创建用户", "user", user.id, f"管理员创建用户 {user.username}")
        return {
            "id": user.id,
            "username": user.username,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "created_at": to_beijing_time(user.created_at).isoformat() if user.created_at else "",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    body: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    detail_parts: list[str] = []

    if "new_password" in body:
        raw = body.get("new_password")
        if not isinstance(raw, str) or len(raw) < 6 or len(raw) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="新密码长度须在 6～100 位之间",
            )
        if user_id == admin.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能在此重置自己的密码，请使用「修改密码」功能",
            )
        admin_set_user_password(db, user, raw, commit=False)
        detail_parts.append("重置密码")

    if "is_active" in body:
        want_active = bool(body["is_active"])
        if want_active != user.is_active:
            if not want_active:
                if user_id == admin.id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能停用自己的账号")
                if user.is_admin:
                    others = (
                        db.query(User)
                        .filter(
                            User.is_admin.is_(True),
                            User.is_active.is_(True),
                            User.id != user_id,
                        )
                        .count()
                    )
                    if others == 0:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="至少需要保留一名可用的管理员",
                        )
                user.is_active = False
                user.password_rev = int(user.password_rev or 0) + 1
                detail_parts.append("停用")
            else:
                user.is_active = True
                detail_parts.append("启用")

    if "is_admin" in body:
        new_admin = bool(body["is_admin"])
        if new_admin != user.is_admin:
            user.is_admin = new_admin
            detail_parts.append(f"管理员={user.is_admin}")

    db.commit()
    db.refresh(user)
    log_detail = f"更新用户 {user.username}"
    if detail_parts:
        log_detail += ": " + ", ".join(detail_parts)
    if detail_parts == ["重置密码"]:
        log_operation(
            db,
            admin.id,
            "重置用户密码",
            "user",
            user.id,
            f"管理员重置用户 {user.username} 的登录密码",
        )
    else:
        log_operation(db, admin.id, "管理用户", "user", user.id, log_detail)

    return {
        "id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "created_at": to_beijing_time(user.created_at).isoformat() if user.created_at else "",
    }

@router.get("/users/{user_id}/org", response_model=AdminUserOrgResponse)
def admin_get_user_org(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return get_user_org(db, user_id)


@router.put("/users/{user_id}/org", response_model=AdminUserOrgResponse)
def admin_put_user_org(
    user_id: int,
    body: AdminUserOrgUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    data = update_user_org(
        db,
        user_id,
        primary_department_id=body.primary_department_id,
        group_ids=body.group_ids,
    )
    db.commit()
    log_operation(
        db,
        admin.id,
        "更新用户组织",
        "user",
        user_id,
        f"dept={data['primary_department_id']} groups={len(data['groups'])}",
    )
    return data

