# Copyright (c) 2026 徐泽宇
"""107 agent run trace API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_api_key_user, get_current_user
from models.user import User
from schemas.agent_run import (
    AgentRunCreateRequest,
    AgentRunCreateResponse,
    AgentRunDeleteRequest,
    AgentRunDeleteResponse,
    AgentRunDetailResponse,
    AgentRunEnsureResponse,
    AgentRunEventAssigned,
    AgentRunEventOut,
    AgentRunEventsBatchRequest,
    AgentRunEventsBatchResponse,
    AgentRunEventsDeltaResponse,
    AgentRunListResponse,
    AgentRunPatchRequest,
    AgentRunSummary,
)
from services.agent_run_service import (
    _event_dict,
    all_events,
    append_events,
    build_view_url,
    create_agent_run,
    delete_agent_runs,
    ensure_session_run,
    get_run_for_viewer,
    iter_run_sse,
    list_agent_runs,
    list_events,
    patch_agent_run,
    resolve_api_key_id,
)

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)


def _require_run(db: Session, run_id: str, viewer: User):
    run = get_run_for_viewer(db, run_id, viewer)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="运行记录不存在")
    return run


@router.post("/ensure", response_model=AgentRunEnsureResponse)
def post_agent_run_ensure(
    body: AgentRunCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_api_key_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    api_key_id = None
    if credentials is not None:
        api_key_id = resolve_api_key_id(db, credentials.credentials)
    run, created = ensure_session_run(db, user, body, api_key_id=api_key_id)
    return AgentRunEnsureResponse(
        run_id=run.id,
        view_url=build_view_url(run.id),
        created=created,
    )


@router.post("", response_model=AgentRunCreateResponse, status_code=status.HTTP_201_CREATED)
def post_agent_run(
    body: AgentRunCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_api_key_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    api_key_id = None
    if credentials is not None:
        api_key_id = resolve_api_key_id(db, credentials.credentials)
    run = create_agent_run(db, user, body, api_key_id=api_key_id)
    return AgentRunCreateResponse(run_id=run.id, view_url=build_view_url(run.id))


@router.post("/{run_id}/events", response_model=AgentRunEventsBatchResponse)
def post_agent_run_events(
    run_id: str,
    body: AgentRunEventsBatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_api_key_user),
):
    run = _require_run(db, run_id, user)
    if run.status != "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="运行已结束")
    assigned = append_events(db, run, body.events)
    return AgentRunEventsBatchResponse(
        assigned=[AgentRunEventAssigned(client_event_id=cid, seq=seq) for cid, seq in assigned]
    )


@router.patch("/{run_id}", response_model=AgentRunSummary)
def patch_agent_run_endpoint(
    run_id: str,
    body: AgentRunPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_api_key_user),
):
    run = _require_run(db, run_id, user)
    run = patch_agent_run(db, run, body)
    return AgentRunSummary.model_validate(run)


@router.get("", response_model=AgentRunListResponse)
def list_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    thread_id: str | None = None,
    status: str | None = None,
    user_id: int | None = Query(None),
    all_users: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    total, items = list_agent_runs(
        db,
        user,
        page=page,
        page_size=page_size,
        thread_id=thread_id,
        status=status,
        user_id=user_id,
        all_users=all_users,
    )
    user_ids = {r.user_id for r in items}
    username_map: dict[int, str] = {}
    if user_ids:
        rows = db.query(User.id, User.username).filter(User.id.in_(user_ids)).all()
        username_map = {uid: uname for uid, uname in rows}
    result_items: list[AgentRunSummary] = []
    for r in items:
        s = AgentRunSummary.model_validate(r)
        s.username = username_map.get(r.user_id)
        result_items.append(s)
    return AgentRunListResponse(
        total=total,
        items=result_items,
    )


@router.post("/delete", response_model=AgentRunDeleteResponse)
def delete_runs_batch(
    body: AgentRunDeleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deleted = delete_agent_runs(db, user, body.ids)
    return AgentRunDeleteResponse(deleted=deleted)


@router.get("/{run_id}", response_model=AgentRunDetailResponse)
def get_run_detail(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = _require_run(db, run_id, user)
    events = all_events(db, run)
    return AgentRunDetailResponse(
        **AgentRunSummary.model_validate(run).model_dump(),
        events=[AgentRunEventOut.model_validate(e) for e in events],
    )


@router.get("/{run_id}/events", response_model=AgentRunEventsDeltaResponse)
def get_run_events_delta(
    run_id: str,
    since_seq: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = _require_run(db, run_id, user)
    rows, latest = list_events(db, run, since_seq=since_seq)
    return AgentRunEventsDeltaResponse(
        events=[AgentRunEventOut.model_validate(e) for e in rows],
        run_status=run.status,
        latest_seq=latest,
    )


@router.get("/{run_id}/stream")
async def stream_run_events(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = _require_run(db, run_id, user)
    initial_events = [
        {"type": "event", "event": _event_dict(row)}
        for row in all_events(db, run)
    ]
    return StreamingResponse(
        iter_run_sse(
            run_id=run.id,
            run_status=run.status,
            initial_events=initial_events,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
