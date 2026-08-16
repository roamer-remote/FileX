# Copyright (c) 2026 徐泽宇
"""settings HTTP 路由模块。

Authors:
    徐泽宇
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.user import User
from schemas.system_setting import ClientSettingsResponse
from schemas.user_setting import (
    UserPreferencesResetRequest,
    UserPreferencesResponse,
    UserPreferencesUpdate,
)
from services.system_setting_service import (
    get_client_settings_dict,
    get_public_settings_dict,
    KEY_AGENT_SKILL_INSTALL_PROMPT,
    DEFAULTS,
)
from services.user_setting_service import (
    USER_SETTING_KEYS,
    build_user_preferences_payload,
    reset_user_settings,
    update_user_settings,
)
from utils.redis_client import (
    get_redis,
    redis_enabled,
    AGENT_SKILL_INSTALL_PROMPT_KEY,
    AGENT_SKILL_INSTALL_PROMPT_TTL,
)

router = APIRouter()


class AgentSkillInstallPromptResponse(BaseModel):
    prompt: str


class AgentSkillInstallPromptRequest(BaseModel):
    api_key: str = ""
    origin: str = ""


@router.post("/agent-skill-install-prompt", response_model=AgentSkillInstallPromptResponse)
def post_agent_skill_install_prompt(
    body: AgentSkillInstallPromptRequest,
    db: Session = Depends(get_db),
):
    """公开接口：返回智能体技能安装提示文本。支持 Redis 缓存。"""
    # Try Redis cache first
    if redis_enabled():
        client = get_redis()
        if client is not None:
            cached = client.get(AGENT_SKILL_INSTALL_PROMPT_KEY)
            if cached:
                prompt = _render_prompt(cached, origin=body.origin, api_key=body.api_key)
                return AgentSkillInstallPromptResponse(prompt=prompt)

    # Fall back to DB
    d = get_public_settings_dict(db)
    template = d.get(KEY_AGENT_SKILL_INSTALL_PROMPT, DEFAULTS.get(KEY_AGENT_SKILL_INSTALL_PROMPT, ""))

    # Cache in Redis
    if redis_enabled():
        client = get_redis()
        if client is not None:
            try:
                client.setex(AGENT_SKILL_INSTALL_PROMPT_KEY, AGENT_SKILL_INSTALL_PROMPT_TTL, template)
            except Exception:
                pass

    prompt = _render_prompt(template, origin=body.origin, api_key=body.api_key)
    return AgentSkillInstallPromptResponse(prompt=prompt)


def _render_prompt(template: str, *, origin: str = "", api_key: str = "") -> str:
    """Replace template variables."""
    prompt = template
    if origin:
        prompt = prompt.replace("{{ORIGIN}}", origin.rstrip("/"))
    if api_key:
        prompt = prompt.replace("{{API_KEY}}", api_key)
    return prompt


@router.get("/clipboard", response_model=ClientSettingsResponse)
def get_clipboard_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    d = get_client_settings_dict(db, user_id=current_user.id)
    return ClientSettingsResponse(**d)


@router.get("/user-preferences", response_model=UserPreferencesResponse)
def get_user_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return UserPreferencesResponse(**build_user_preferences_payload(db, current_user.id))


@router.put("/user-preferences", response_model=UserPreferencesResponse)
def put_user_preferences(
    body: UserPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not patch:
        return UserPreferencesResponse(**build_user_preferences_payload(db, current_user.id))
    try:
        update_user_settings(db, current_user.id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UserPreferencesResponse(**build_user_preferences_payload(db, current_user.id))


@router.post("/user-preferences/reset", response_model=UserPreferencesResponse)
def reset_user_preferences(
    body: UserPreferencesResetRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    keys = body.keys if body else None
    if keys is not None:
        unknown = [k for k in keys if k not in USER_SETTING_KEYS]
        if unknown:
            raise HTTPException(status_code=400, detail=f"未知或不可配置参数: {', '.join(unknown)}")
    try:
        reset_user_settings(db, current_user.id, keys)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UserPreferencesResponse(**build_user_preferences_payload(db, current_user.id))
