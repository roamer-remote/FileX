# Copyright (c) 2026 徐泽宇
"""微信开放平台网站应用 OAuth（扫码登录 / 绑定）。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import quote_plus

import httpx
from sqlalchemy.orm import Session

from config import (
    MOCK_WECHAT_OPENID,
    WECHAT_ACCESS_TOKEN_URL,
    WECHAT_APP_ID,
    WECHAT_APP_SECRET,
    WECHAT_AUTHORIZE_URL,
    WECHAT_OAUTH_STATE_TTL_MINUTES,
    WECHAT_REDIRECT_URI,
    WECHAT_USERINFO_URL,
    wechat_configured,
)
from models.user import User
from models.wechat_oauth_state import WeChatOAuthState
from services.auth_service import create_access_token, record_user_login
from services.log_service import log_operation
from services.workspace_service import ensure_personal_workspace
from utils.timezone import beijing_now

logger = logging.getLogger("filex.wechat")

STATUS_PENDING = "pending"
STATUS_SUCCESS = "success"
STATUS_NEED_REGISTER = "need_register"
STATUS_ERROR = "error"
STATUS_CONSUMED = "consumed"
STATUS_AWAITING_BIND_CONFIRM = "awaiting_bind_confirm"
MODE_LOGIN = "login"
MODE_BIND = "bind"
WECHAT_POLL_COOKIE = "filex_wx_poll"


@dataclass
class QrcodeSession:
    """二维码session 业务服务。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-31

        Attributes:
            state: 状态（str）。
            app_id: 应用ID（str）。
            redirect_uri: 重定向URI（str）。
            mock_mode: 模拟mode（bool）。
            poll_token: 轮询凭证（str），仅创建会话的客户端可换取 JWT。
    """
    state: str
    app_id: str
    redirect_uri: str
    mock_mode: bool
    poll_token: str


class WeChatAuthError(Exception):
    """业务可预期错误，detail 可直接返回给客户端。"""


def _now_naive():
    return beijing_now().replace(tzinfo=None)


def _purge_expired_states(db: Session) -> None:
    db.query(WeChatOAuthState).filter(WeChatOAuthState.expires_at < _now_naive()).delete(
        synchronize_session=False
    )


def get_valid_state(db: Session, state: str) -> WeChatOAuthState | None:
    row = db.get(WeChatOAuthState, state)
    if not row or row.expires_at <= _now_naive():
        return None
    return row


def _poll_verified(row: WeChatOAuthState, poll_token: str | None, cookie_poll: str | None) -> bool:
    secret = row.poll_secret
    if not secret:
        return True
    if poll_token and secrets.compare_digest(poll_token, secret):
        return True
    if cookie_poll and secrets.compare_digest(cookie_poll, secret):
        return True
    return False


def _requires_poll_for_status(status: str) -> bool:
    return status in (
        STATUS_SUCCESS,
        STATUS_NEED_REGISTER,
        STATUS_ERROR,
        STATUS_AWAITING_BIND_CONFIRM,
    )


def create_qrcode_session(
    db: Session,
    *,
    mode: str = MODE_LOGIN,
    bind_user_id: int | None = None,
) -> QrcodeSession:
    _purge_expired_states(db)
    state = str(uuid.uuid4())
    poll_secret = secrets.token_urlsafe(32)
    expires_at = _now_naive() + timedelta(minutes=WECHAT_OAUTH_STATE_TTL_MINUTES)
    row = WeChatOAuthState(
        state=state,
        mode=mode or MODE_LOGIN,
        status=STATUS_PENDING,
        bind_user_id=bind_user_id,
        poll_secret=poll_secret,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()

    mock_mode = not wechat_configured()
    app_id = WECHAT_APP_ID if wechat_configured() else "mock_app_id"
    redirect_uri = WECHAT_REDIRECT_URI if wechat_configured() else "http://localhost/api/wechat/callback"
    return QrcodeSession(
        state=state,
        app_id=app_id,
        redirect_uri=redirect_uri,
        mock_mode=mock_mode,
        poll_token=poll_secret,
    )


def user_payload(user: User) -> dict[str, Any]:
    from utils.timezone import to_beijing_time

    return {
        "id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "created_at": to_beijing_time(user.created_at).isoformat() if user.created_at else "",
        "has_avatar": user.avatar_mime is not None,
        "wechat_bound": user.wechat_openid is not None,
        "wechat_nickname": user.wechat_nickname or "",
    }


def _finish_login(db: Session, user: User, row: WeChatOAuthState) -> str:
    if not user.is_active:
        raise WeChatAuthError("账号已停用")
    record_user_login(db, user, commit=False)
    ensure_personal_workspace(db, user)
    row.status = STATUS_SUCCESS
    row.success_user_id = user.id
    log_operation(db, user.id, "微信登录", "user", user.id, f"用户 {user.username} 微信登录")
    db.commit()
    db.refresh(user)
    return create_access_token(user.id, user.password_rev or 0)


def _mark_oauth_error(db: Session, row: WeChatOAuthState, message: str) -> tuple[None, str, str]:
    row.status = STATUS_ERROR
    row.pending_nickname = (message or "操作失败")[:128]
    db.commit()
    return None, STATUS_ERROR, message


def _mark_need_register(
    db: Session,
    row: WeChatOAuthState,
    openid: str,
    unionid: str | None,
    nickname: str | None = None,
) -> None:
    row.status = STATUS_NEED_REGISTER
    row.pending_openid = openid
    row.pending_unionid = unionid
    row.pending_nickname = nickname
    db.commit()


async def _fetch_userinfo(access_token: str, openid: str) -> str | None:
    url = f"{WECHAT_USERINFO_URL}?access_token={access_token}&openid={openid}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url)
        data = resp.json()
    if "errcode" in data:
        return None
    nickname = data.get("nickname")
    return nickname if isinstance(nickname, str) and nickname.strip() else None


async def _exchange_code(code: str) -> tuple[str, str | None, str | None]:
    url = (
        f"{WECHAT_ACCESS_TOKEN_URL}?appid={WECHAT_APP_ID}"
        f"&secret={WECHAT_APP_SECRET}&code={code}&grant_type=authorization_code"
    )
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url)
        data = resp.json()
    if "errcode" in data:
        raise WeChatAuthError(f"微信授权失败: {data.get('errmsg', '未知错误')}")
    access_token = data["access_token"]
    openid = data["openid"]
    unionid = data.get("unionid")
    nickname = await _fetch_userinfo(access_token, openid)
    return openid, unionid, nickname


async def handle_callback(
    db: Session,
    code: str,
    state: str,
) -> tuple[str | None, str, str]:
    row = get_valid_state(db, state)
    if not row:
        return None, STATUS_ERROR, "登录会话已过期或无效，请重新扫码"

    if row.status == STATUS_SUCCESS and row.success_user_id:
        user = db.get(User, row.success_user_id)
        if user:
            token = create_access_token(user.id, user.password_rev or 0)
            return token, "success", "微信登录成功"
        return _mark_oauth_error(db, row, "无效的请求状态")

    if row.status == STATUS_NEED_REGISTER:
        return None, "need_register", "微信已验证，请返回页面完成注册"

    if row.status == STATUS_ERROR:
        return None, STATUS_ERROR, row.pending_nickname or "操作失败"

    if row.status == STATUS_CONSUMED:
        return _mark_oauth_error(db, row, "微信验证已使用或已过期")

    if not wechat_configured():
        return _mark_oauth_error(db, row, "未配置微信登录，请使用开发 mock 接口")

    try:
        openid, unionid, nickname = await _exchange_code(code)
    except WeChatAuthError as e:
        return _mark_oauth_error(db, row, str(e))

    if row.mode == MODE_BIND and row.bind_user_id:
        existing = db.query(User).filter(User.wechat_openid == openid).first()
        if existing and existing.id != row.bind_user_id:
            return _mark_oauth_error(db, row, "该微信账号已绑定到其他用户")
        user = db.get(User, row.bind_user_id)
        if not user:
            return _mark_oauth_error(db, row, "绑定失败，用户不存在")
        row.pending_openid = openid
        row.pending_unionid = unionid
        row.pending_nickname = nickname
        row.status = STATUS_AWAITING_BIND_CONFIRM
        db.commit()
        return None, STATUS_AWAITING_BIND_CONFIRM, "微信已验证，请在网页上确认绑定"

    user = db.query(User).filter(User.wechat_openid == openid).first()
    if user:
        token = _finish_login(db, user, row)
        return token, "success", "微信登录成功"

    _mark_need_register(db, row, openid, unionid, nickname)
    return None, "need_register", "微信已验证，请返回页面完成注册"


def handle_mock_callback(
    db: Session,
    state: str,
    scenario: str,
) -> tuple[str | None, str, str]:
    row = get_valid_state(db, state)
    if not row:
        return None, STATUS_ERROR, "登录会话已过期或无效，请重新扫码"
    if row.status == STATUS_ERROR:
        return None, STATUS_ERROR, row.pending_nickname or "操作失败"
    if row.mode == MODE_BIND and row.bind_user_id:
        existing = db.query(User).filter(User.wechat_openid == MOCK_WECHAT_OPENID).first()
        if existing and existing.id != row.bind_user_id:
            return _mark_oauth_error(db, row, "该微信账号已绑定到其他用户")
        user = db.get(User, row.bind_user_id)
        if not user:
            return _mark_oauth_error(db, row, "绑定失败，用户不存在")
        row.pending_openid = MOCK_WECHAT_OPENID
        row.pending_unionid = None
        row.pending_nickname = "模拟微信用户"
        row.status = STATUS_AWAITING_BIND_CONFIRM
        db.commit()
        return None, STATUS_AWAITING_BIND_CONFIRM, "微信已验证，请在网页上确认绑定（开发模式）"

    if scenario == "need_register":
        _mark_need_register(db, row, MOCK_WECHAT_OPENID, None, "模拟微信用户")
        return None, "need_register", "微信已验证，请返回页面完成注册（开发模式）"

    user = db.query(User).filter(User.wechat_openid == MOCK_WECHAT_OPENID).first()
    if not user:
        return _mark_oauth_error(db, row, "模拟已绑定登录需要库中存在 wechat_openid=mock_openid_dev 的用户")
    token = _finish_login(db, user, row)
    return token, "success", "微信登录成功（开发模式）"


def check_login_status(
    db: Session,
    state: str,
    *,
    poll_token: str | None = None,
    cookie_poll: str | None = None,
) -> dict[str, Any]:
    row = get_valid_state(db, state)
    if not row:
        return {"status": "invalid"}

    if _requires_poll_for_status(row.status) and not _poll_verified(row, poll_token, cookie_poll):
        return {"status": STATUS_PENDING}

    if row.status == STATUS_SUCCESS and row.success_user_id:
        user = db.get(User, row.success_user_id)
        if user:
            token = create_access_token(user.id, user.password_rev or 0)
            return {
                "status": STATUS_SUCCESS,
                "access_token": token,
                "user": user_payload(user),
            }

    if row.status == STATUS_AWAITING_BIND_CONFIRM:
        nickname = row.pending_nickname or ""
        return {
            "status": STATUS_AWAITING_BIND_CONFIRM,
            "wechat_nickname": nickname,
        }

    if row.status == STATUS_NEED_REGISTER:
        return {"status": STATUS_NEED_REGISTER}

    if row.status == STATUS_ERROR:
        return {"status": STATUS_ERROR, "message": row.pending_nickname or "操作失败"}

    return {"status": row.status}


def confirm_wechat_bind(
    db: Session,
    user: User,
    state: str,
    *,
    poll_token: str | None = None,
    cookie_poll: str | None = None,
) -> dict[str, Any]:
    row = get_valid_state(db, state)
    if not row:
        raise WeChatAuthError("登录会话已过期或无效，请重新扫码")
    if row.mode != MODE_BIND or row.bind_user_id != user.id:
        raise WeChatAuthError("无效的绑定请求")
    if row.status != STATUS_AWAITING_BIND_CONFIRM:
        raise WeChatAuthError("微信验证已使用或无效")
    if not _poll_verified(row, poll_token, cookie_poll):
        raise WeChatAuthError("绑定确认凭证无效")
    if not row.pending_openid:
        raise WeChatAuthError("微信验证数据无效")

    existing = db.query(User).filter(User.wechat_openid == row.pending_openid).first()
    if existing and existing.id != user.id:
        raise WeChatAuthError("该微信账号已绑定到其他用户")

    from services.auth_service import bind_wechat

    bind_wechat(
        db,
        user,
        row.pending_openid,
        row.pending_unionid,
        row.pending_nickname,
        commit=False,
    )
    row.status = STATUS_SUCCESS
    row.success_user_id = user.id
    log_operation(db, user.id, "微信绑定", "user", user.id, f"用户 {user.username} 绑定微信")
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.password_rev or 0)
    return {
        "status": STATUS_SUCCESS,
        "access_token": token,
        "user": user_payload(user),
    }


def consume_state_for_register(
    db: Session,
    state_value: str,
    user: User,
) -> None:
    row = db.get(WeChatOAuthState, state_value)
    if not row or row.expires_at <= _now_naive():
        raise ValueError("微信验证已过期，请重新扫码")
    if row.status != STATUS_NEED_REGISTER:
        raise ValueError("微信验证已使用或无效")
    if not row.pending_openid:
        raise ValueError("微信验证数据无效")

    existing = db.query(User).filter(User.wechat_openid == row.pending_openid).first()
    if existing:
        raise ValueError("该微信账号已绑定到其他用户")

    from services.auth_service import bind_wechat

    bind_wechat(db, user, row.pending_openid, row.pending_unionid, row.pending_nickname, commit=False)
    row.status = STATUS_CONSUMED
    row.success_user_id = user.id
    row.consumed_at = _now_naive()
