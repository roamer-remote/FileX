# Copyright (c) 2026 徐泽宇
"""wechat HTTP 路由模块。

Authors:
    徐泽宇
"""

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import WECHAT_OAUTH_STATE_TTL_MINUTES, wechat_configured
from database import get_db
from middleware.auth import get_current_user
from models.user import User
from services.wechat_service import (
    MODE_BIND,
    STATUS_AWAITING_BIND_CONFIRM,
    WECHAT_POLL_COOKIE,
    WeChatAuthError,
    check_login_status,
    confirm_wechat_bind,
    create_qrcode_session,
    handle_callback,
    handle_mock_callback,
)

router = APIRouter()
logger = logging.getLogger("filex.wechat")


class WechatConfirmBindRequest(BaseModel):
    state: str = Field(..., min_length=1)
    poll_token: str | None = None


def _attach_poll_cookie(response: Response, poll_token: str) -> None:
    response.set_cookie(
        key=WECHAT_POLL_COOKIE,
        value=poll_token,
        httponly=True,
        samesite="lax",
        max_age=WECHAT_OAUTH_STATE_TTL_MINUTES * 60,
        path="/api/wechat",
    )


def _session_payload(session) -> dict:
    return {
        "state": session.state,
        "app_id": session.app_id,
        "redirect_uri": session.redirect_uri,
        "mock_mode": session.mock_mode,
        "poll_token": session.poll_token,
    }


def _callback_html(message: str, token: str | None = None, kind: str = "success") -> str:
    token_js = f'"{token}"' if token else "null"
    kind_js = f'"{kind}"'
    safe_message = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    message_js = json.dumps(message, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="light dark" />
  <title>微信授权</title>
  <style>
    html, body {{
      margin: 0;
      min-height: 100%;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }}
    body {{
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 24px;
      box-sizing: border-box;
    }}
    html[data-theme="dark"], html[data-theme="dark"] body {{
      background: #1c1c1e;
      color: #f5f5f7;
    }}
    html[data-theme="light"], html[data-theme="light"] body {{
      background: #f5f5f7;
      color: #1c1c1e;
    }}
    #msg {{
      margin: 0;
      font-size: 16px;
      font-weight: 500;
      letter-spacing: -0.2px;
      max-width: 320px;
      line-height: 1.5;
    }}
    body.in-iframe #msg {{
      display: none;
    }}
  </style>
  <script>
    (function () {{
      var dark = false;
      try {{
        var root = window.top && window.top.document && window.top.document.documentElement;
        if (root) {{
          dark = root.getAttribute("data-theme") === "dark";
        }}
      }} catch (e) {{
        dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      }}
      document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
      function markIframe() {{
        if (document.body) document.body.classList.add("in-iframe");
      }}
      try {{
        if (window.self !== window.top) markIframe();
      }} catch (e) {{
        markIframe();
      }}
    }})();
  </script>
</head>
<body>
  <p id="msg">{safe_message}</p>
  <script>
    (function () {{
      var token = {token_js};
      var kind = {kind_js};
      var inFrame = false;
      try {{
        inFrame = window.self !== window.top;
      }} catch (e) {{
        inFrame = true;
      }}
      try {{
        if (token && window.top && window.top.localStorage) {{
          window.top.localStorage.setItem("filex_wechat_callback_token", token);
        }} else if (token && window.localStorage) {{
          window.localStorage.setItem("filex_wechat_callback_token", token);
        }}
      }} catch (e) {{}}
      try {{
        if (inFrame && window.top) {{
          window.top.postMessage(
            {{
              type: "filex_wechat_callback",
              token: token,
              kind: kind,
              message: {message_js}
            }},
            window.location.origin
          );
          return;
        }}
        if (token) window.location.href = "/";
      }} catch (e) {{}}
    }})();
  </script>
</body>
</html>"""


@router.get("/qrcode")
def get_qrcode(response: Response, db: Session = Depends(get_db)):
    session = create_qrcode_session(db, mode="login")
    _attach_poll_cookie(response, session.poll_token)
    return _session_payload(session)


@router.get("/bind-qrcode")
def get_bind_qrcode(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.wechat_openid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已绑定微信")
    session = create_qrcode_session(db, mode=MODE_BIND, bind_user_id=current_user.id)
    _attach_poll_cookie(response, session.poll_token)
    return _session_payload(session)


@router.get("/status/{state}")
def get_status(
    state: str,
    request: Request,
    poll_token: str | None = Query(None),
    db: Session = Depends(get_db),
):
    cookie_poll = request.cookies.get(WECHAT_POLL_COOKIE)
    return check_login_status(db, state, poll_token=poll_token, cookie_poll=cookie_poll)


@router.post("/confirm-bind")
def post_confirm_bind(
    body: WechatConfirmBindRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cookie_poll = request.cookies.get(WECHAT_POLL_COOKIE)
    try:
        return confirm_wechat_bind(
            db,
            current_user,
            body.state,
            poll_token=body.poll_token,
            cookie_poll=cookie_poll,
        )
    except WeChatAuthError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/callback")
async def wechat_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        token, kind, message = await handle_callback(db, code, state)
    except WeChatAuthError as e:
        return HTMLResponse(content=_callback_html(str(e), token=None, kind="error"), status_code=200)

    if kind == "error":
        return HTMLResponse(content=_callback_html(message, token=None, kind=kind), status_code=200)
    if kind == "need_register":
        return HTMLResponse(content=_callback_html(message, token=None, kind=kind), status_code=200)
    if kind == STATUS_AWAITING_BIND_CONFIRM:
        return HTMLResponse(content=_callback_html(message, token=None, kind=kind), status_code=200)
    return HTMLResponse(content=_callback_html(message, token=token, kind=kind), status_code=200)


@router.get("/mock-callback")
def mock_callback(
    state: str = Query(...),
    scenario: str = Query("need_register", pattern="^(need_register|login)$"),
    db: Session = Depends(get_db),
):
    if wechat_configured():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="生产环境已配置微信")
    if os.environ.get("FILEX_ENV", "").strip() != "development":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅 development 可用")
    try:
        token, kind, message = handle_mock_callback(db, state, scenario)
    except WeChatAuthError as e:
        return HTMLResponse(content=_callback_html(str(e), token=None, kind="error"), status_code=200)
    if kind == "error":
        return HTMLResponse(content=_callback_html(message, token=None, kind=kind), status_code=200)
    if kind == "need_register":
        return HTMLResponse(content=_callback_html(message, token=None, kind=kind), status_code=200)
    if kind == STATUS_AWAITING_BIND_CONFIRM:
        return HTMLResponse(content=_callback_html(message, token=None, kind=kind), status_code=200)
    return HTMLResponse(content=_callback_html(message, token=token, kind=kind), status_code=200)
