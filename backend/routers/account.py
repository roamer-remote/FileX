# Copyright (c) 2026 徐泽宇
"""039 /api/account — 用户 UI 状态。"""

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models.user import User
from schemas.user_ui_state import UiStatePatch, UiStateResponse, UserUiStateV1
from services.user_ui_state_service import (
    StateTooLargeError,
    get_ui_state,
    merge_ui_state,
    migrate_ui_state,
)

router = APIRouter()


@router.get("/ui-state", response_model=UiStateResponse)
def get_account_ui_state(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    state, updated_at = get_ui_state(db, current_user.id)
    if state is None:
        return UiStateResponse(state=UserUiStateV1(), updated_at=None)
    return UiStateResponse(state=UserUiStateV1.model_validate(state), updated_at=updated_at)


@router.put("/ui-state", response_model=UiStateResponse)
def put_account_ui_state(
    body: UiStatePatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patch = body.model_dump(exclude_unset=True)
    try:
        state, updated_at = merge_ui_state(db, current_user.id, patch)
    except StateTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UiStateResponse(state=UserUiStateV1.model_validate(state), updated_at=updated_at)


@router.post("/ui-state/migrate", response_model=UiStateResponse)
def post_account_ui_state_migrate(
    body: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 接受 localStorage 快照（含小数坐标等），由 service 归一化后再校验
    snapshot = body
    try:
        state, updated_at = migrate_ui_state(db, current_user.id, snapshot)
    except StateTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UiStateResponse(state=UserUiStateV1.model_validate(state), updated_at=updated_at)
