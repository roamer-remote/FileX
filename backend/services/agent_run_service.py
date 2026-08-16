# Copyright (c) 2026 徐泽宇
"""107 agent run trace service."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from config import API_KEY_PREFIX
from models.agent_run import AgentRun, AgentRunEvent
from models.api_key import ApiKey
from models.user import User
from schemas.agent_run import (
    AgentRunCreateRequest,
    AgentRunEventIn,
    AgentRunPatchRequest,
)
from utils.timezone import beijing_now

DEFAULT_AGENT_RUN_RETENTION_DAYS = 30
AGENT_RUN_RETENTION_DAYS_MIN = 1
AGENT_RUN_RETENTION_DAYS_MAX = 365
KB_SEARCH_TRACE_SESSION_MINUTES = 15

META_ALLOWLIST = frozenset(
    {
        "file_id",
        "file_ids",
        "hit_count",
        "search_round",
        "duration_ms",
        "error_code",
        "module_hint",
        "intent",
        "gap",
        "parallel_group",
        "result_count",
        "vlm_round",
        "wiki_expanded",
        "search_trace_summary",
        "trace_id",
    }
)

META_DENYLIST = frozenset(
    {
        "query",
        "prompt",
        "question",
        "user_question",
        "markdown",
        "md_content",
        "text",
        "context_text",
        "authorization",
        "token",
        "api_key",
        "bearer",
        "password",
        "secret",
    }
)


class _StreamHub:
    """In-process SSE fan-out per run_id (thread-safe publish → asyncio.Queue)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[str, set[tuple[asyncio.Queue[dict[str, Any] | None], asyncio.AbstractEventLoop | None]]] = (
            defaultdict(set)
        )

    def subscribe(self, run_id: str) -> asyncio.Queue[dict[str, Any] | None]:
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        with self._lock:
            self._subs[run_id].add((q, loop))
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue[dict[str, Any] | None]) -> None:
        with self._lock:
            subs = self._subs.get(run_id)
            if subs is None:
                return
            self._subs[run_id] = {(queue, loop) for queue, loop in subs if queue is not q}
            if not self._subs[run_id]:
                self._subs.pop(run_id, None)

    @staticmethod
    def _deliver(q: asyncio.Queue[dict[str, Any] | None], payload: dict[str, Any] | None) -> None:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass

    def publish(self, run_id: str, payload: dict[str, Any] | None) -> None:
        with self._lock:
            subs = list(self._subs.get(run_id, ()))
        for q, loop in subs:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(self._deliver, q, payload)
            else:
                self._deliver(q, payload)


stream_hub = _StreamHub()


def agent_run_retention_days(db: Session | None = None) -> int:
    env_raw = (os.environ.get("AGENT_RUN_RETENTION_DAYS") or "").strip()
    if env_raw.isdigit():
        return max(AGENT_RUN_RETENTION_DAYS_MIN, min(AGENT_RUN_RETENTION_DAYS_MAX, int(env_raw)))
    if db is not None:
        from services.system_setting_service import get_agent_run_retention_days

        return get_agent_run_retention_days(db)
    return DEFAULT_AGENT_RUN_RETENTION_DAYS


def filex_origin_base() -> str:
    return (os.environ.get("FILEX_ORIGIN") or "").rstrip("/")


def build_view_url(run_id: str) -> str:
    origin = filex_origin_base()
    path = f"/agent/runs/{run_id}"
    return f"{origin}{path}" if origin else path


def truncate_question_preview(text: str) -> str:
    one = " ".join((text or "").split())
    if len(one) <= 120:
        return one
    return f"{one[:117]}…"


def sanitize_meta_json(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    if not meta:
        return None
    out: dict[str, Any] = {}
    for key, value in meta.items():
        k = str(key).strip().lower()
        if k in META_DENYLIST:
            continue
        if k not in META_ALLOWLIST:
            continue
        out[key] = value
    return out or None


def resolve_api_key_id(db: Session, bearer: str) -> int | None:
    key = (bearer or "").strip()
    if not key.startswith(API_KEY_PREFIX):
        return None
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    row = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
    return int(row.id) if row else None


def _expires_at_from_now(db: Session) -> datetime:
    return beijing_now().replace(tzinfo=None) + timedelta(days=agent_run_retention_days(db))


def _search_task_key(question_preview: str) -> str:
    normalized = " ".join((question_preview or "").split()).lower()
    fp = hashlib.sha256(normalized.encode()).hexdigest()[:12]
    return f"search:{fp}"


def get_running_run_for_user(
    db: Session,
    user: User,
    run_id: str,
) -> AgentRun | None:
    now = beijing_now().replace(tzinfo=None)
    run = (
        db.query(AgentRun)
        .filter(
            AgentRun.id == run_id.strip(),
            AgentRun.user_id == int(user.id),
            AgentRun.status == "running",
        )
        .first()
    )
    if run is None:
        return None
    if run.expires_at and run.expires_at < now:
        return None
    return run


def ensure_session_run(
    db: Session,
    user: User,
    body: AgentRunCreateRequest,
    *,
    api_key_id: int | None = None,
) -> tuple[AgentRun, bool]:
    """109：同 thread_id（或无 thread 时同 Key 窗口）复用 running run。"""
    now = beijing_now().replace(tzinfo=None)
    tid = (body.thread_id or "").strip() or None
    run: AgentRun | None = None
    if tid:
        run = (
            db.query(AgentRun)
            .filter(
                AgentRun.user_id == int(user.id),
                AgentRun.thread_id == tid,
                AgentRun.status == "running",
            )
            .order_by(AgentRun.started_at.desc())
            .first()
        )
    elif api_key_id is not None:
        window_start = now - timedelta(minutes=KB_SEARCH_TRACE_SESSION_MINUTES)
        run = (
            db.query(AgentRun)
            .filter(
                AgentRun.user_id == int(user.id),
                AgentRun.api_key_id == int(api_key_id),
                AgentRun.status == "running",
                AgentRun.started_at >= window_start,
            )
            .order_by(AgentRun.started_at.desc())
            .first()
        )
    if run is not None and run.expires_at and run.expires_at < now:
        run.status = "failed"
        if run.finished_at is None:
            run.finished_at = now
        db.commit()
        run = None
    if run is not None:
        return run, False
    created = create_agent_run(db, user, body, api_key_id=api_key_id)
    return created, True


def create_agent_run(
    db: Session,
    user: User,
    body: AgentRunCreateRequest,
    *,
    api_key_id: int | None = None,
) -> AgentRun:
    run = AgentRun(
        user_id=int(user.id),
        api_key_id=api_key_id,
        thread_id=(body.thread_id or "").strip() or None,
        question_preview=truncate_question_preview(body.question_preview),
        intent=(body.intent or "").strip() or None,
        status="running",
        expires_at=_expires_at_from_now(db),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run_for_viewer(db: Session, run_id: str, viewer: User) -> AgentRun | None:
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if run is None:
        return None
    if int(run.user_id) != int(viewer.id):
        return None
    if run.expires_at and run.expires_at < beijing_now().replace(tzinfo=None):
        return None
    return run


def list_agent_runs(
    db: Session,
    viewer: User,
    *,
    page: int = 1,
    page_size: int = 20,
    thread_id: str | None = None,
    status: str | None = None,
    user_id: int | None = None,
    all_users: bool = False,
) -> tuple[int, list[AgentRun]]:
    now = beijing_now().replace(tzinfo=None)
    q = db.query(AgentRun)
    if viewer.is_admin and all_users:
        q = q.filter(AgentRun.expires_at >= now)
    elif viewer.is_admin and user_id is not None:
        q = q.filter(
            AgentRun.user_id == user_id,
            AgentRun.expires_at >= now,
        )
    else:
        q = q.filter(
            AgentRun.user_id == int(viewer.id),
            AgentRun.expires_at >= now,
        )
    if thread_id:
        q = q.filter(AgentRun.thread_id == thread_id.strip())
    if status:
        q = q.filter(AgentRun.status == status.strip())
    total = q.count()
    items = (
        q.order_by(AgentRun.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return total, items


def _client_seq_map(db: Session, run_id: str) -> dict[str, int]:
    rows = (
        db.query(AgentRunEvent.client_event_id, AgentRunEvent.seq)
        .filter(
            AgentRunEvent.run_id == run_id,
            AgentRunEvent.client_event_id.isnot(None),
        )
        .all()
    )
    return {str(cid): int(seq) for cid, seq in rows if cid}


def append_events(
    db: Session,
    run: AgentRun,
    events: list[AgentRunEventIn],
) -> list[tuple[str | None, int]]:
    if not events:
        return []

    locked = (
        db.query(AgentRun)
        .filter(AgentRun.id == run.id)
        .with_for_update()
        .one()
    )
    max_seq = (
        db.query(func.max(AgentRunEvent.seq))
        .filter(AgentRunEvent.run_id == locked.id)
        .scalar()
    ) or 0
    client_map = _client_seq_map(db, locked.id)
    assigned: list[tuple[str | None, int]] = []
    created_rows: list[AgentRunEvent] = []

    for ev in events:
        if ev.client_event_id and ev.client_event_id in client_map:
            assigned.append((ev.client_event_id, client_map[ev.client_event_id]))
            continue

        max_seq += 1
        parent_seq: int | None = None
        if ev.parent_client_event_id:
            parent_seq = client_map.get(ev.parent_client_event_id)

        ts = ev.ts or beijing_now().replace(tzinfo=None)
        row = AgentRunEvent(
            run_id=locked.id,
            seq=max_seq,
            client_event_id=ev.client_event_id,
            parent_seq=parent_seq,
            task_key=ev.task_key,
            span_id=ev.span_id,
            attempt=max(1, int(ev.attempt or 1)),
            ts=ts,
            layer=ev.layer,
            node_id=ev.node_id,
            label=ev.label,
            phase=ev.phase,
            duration_ms=ev.duration_ms,
            meta_json=sanitize_meta_json(ev.meta),
        )
        db.add(row)
        created_rows.append(row)
        if ev.client_event_id:
            client_map[ev.client_event_id] = max_seq
        assigned.append((ev.client_event_id, max_seq))

    db.commit()
    for row in created_rows:
        db.refresh(row)
        stream_hub.publish(
            locked.id,
            {
                "type": "event",
                "event": _event_dict(row),
            },
        )
    return assigned


def patch_agent_run(db: Session, run: AgentRun, body: AgentRunPatchRequest) -> AgentRun:
    now = beijing_now().replace(tzinfo=None)
    run.status = body.status
    if body.summary_json is not None:
        run.summary_json = body.summary_json
    if body.duration_ms is not None:
        run.duration_ms = body.duration_ms
    if run.finished_at is None:
        run.finished_at = now
        if run.duration_ms is None and run.started_at:
            delta = now - run.started_at
            run.duration_ms = int(delta.total_seconds() * 1000)
    db.commit()
    db.refresh(run)
    stream_hub.publish(run.id, {"type": "run_status", "status": run.status})
    stream_hub.publish(run.id, None)
    return run


def list_events(
    db: Session,
    run: AgentRun,
    *,
    since_seq: int = 0,
) -> tuple[list[AgentRunEvent], int]:
    rows = (
        db.query(AgentRunEvent)
        .filter(AgentRunEvent.run_id == run.id, AgentRunEvent.seq > since_seq)
        .order_by(AgentRunEvent.seq.asc())
        .all()
    )
    latest = (
        db.query(func.max(AgentRunEvent.seq))
        .filter(AgentRunEvent.run_id == run.id)
        .scalar()
    ) or 0
    return rows, int(latest)


def all_events(db: Session, run: AgentRun) -> list[AgentRunEvent]:
    return (
        db.query(AgentRunEvent)
        .filter(AgentRunEvent.run_id == run.id)
        .order_by(AgentRunEvent.seq.asc())
        .all()
    )


def _event_dict(row: AgentRunEvent) -> dict[str, Any]:
    return {
        "seq": row.seq,
        "client_event_id": row.client_event_id,
        "parent_seq": row.parent_seq,
        "task_key": row.task_key,
        "span_id": row.span_id,
        "attempt": row.attempt,
        "ts": row.ts.isoformat() if row.ts else None,
        "layer": row.layer,
        "node_id": row.node_id,
        "label": row.label,
        "phase": row.phase,
        "duration_ms": row.duration_ms,
        "meta_json": row.meta_json,
    }


def trace_kb_search(
    db: Session,
    user: User,
    *,
    thread_id: str | None,
    question_preview: str,
    hit_count: int,
    api_key_id: int | None = None,
    agent_run_id: str | None = None,
    search_trace_id: str | None = None,
    duration_ms: int | None = None,
) -> str | None:
    """109 fail-open：API Key search 追加到会话 run，search 分支 start/end 成对。"""
    if api_key_id is None and not (agent_run_id or "").strip():
        return None
    try:
        tid = (thread_id or "").strip() or None
        run: AgentRun | None = None
        explicit_id = (agent_run_id or "").strip()
        if explicit_id:
            run = get_running_run_for_user(db, user, explicit_id)
            if run is None:
                return None
        else:
            if api_key_id is None:
                return None
            run, _ = ensure_session_run(
                db,
                user,
                AgentRunCreateRequest(
                    question_preview=question_preview,
                    thread_id=tid,
                ),
                api_key_id=api_key_id,
            )
        task_key = _search_task_key(question_preview)
        span_id = str(uuid.uuid4())
        append_events(
            db,
            run,
            [
                AgentRunEventIn(
                    layer="tool",
                    node_id="kb_search",
                    label="资料库检索",
                    phase="start",
                    task_key=task_key,
                    span_id=span_id,
                ),
                AgentRunEventIn(
                    layer="tool",
                    node_id="kb_search",
                    label="资料库检索",
                    phase="end",
                    task_key=task_key,
                    span_id=span_id,
                    duration_ms=duration_ms,
                    meta={
                        "hit_count": hit_count,
                        "trace_id": (search_trace_id or "").strip() or None,
                    },
                ),
            ],
        )
        return build_view_url(run.id)
    except Exception:
        return None


def purge_expired_agent_runs(db: Session) -> int:
    now = beijing_now().replace(tzinfo=None)
    q = db.query(AgentRun).filter(AgentRun.expires_at < now)
    count = q.count()
    if count:
        q.delete(synchronize_session=False)
        db.commit()
    return count


def delete_agent_runs(db: Session, viewer: User, run_ids: list[str]) -> int:
    unique_ids = list(dict.fromkeys(rid.strip() for rid in run_ids if rid and rid.strip()))
    if not unique_ids:
        return 0
    filters = [AgentRun.id.in_(unique_ids)]
    if not viewer.is_admin:
        filters.append(AgentRun.user_id == int(viewer.id))
    rows = db.query(AgentRun).filter(*filters).all()
    if not rows:
        return 0
    deleted_ids = [row.id for row in rows]
    db.query(AgentRun).filter(AgentRun.id.in_(deleted_ids)).delete(synchronize_session=False)
    db.commit()
    for run_id in deleted_ids:
        stream_hub.publish(run_id, None)
    return len(deleted_ids)


async def iter_run_sse(
    *,
    run_id: str,
    run_status: str,
    initial_events: list[dict[str, Any]],
):
    """Async generator for SSE stream (snapshot from request-scoped DB session)."""
    queue = stream_hub.subscribe(run_id)
    try:
        for payload in initial_events:
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        if run_status != "running":
            yield f"event: close\ndata: {json.dumps({'status': run_status})}\n\n"
            return

        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=25.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if msg is None:
                yield f"event: close\ndata: {{}}\n\n"
                break
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            if msg.get("type") == "run_status":
                yield f"event: close\ndata: {json.dumps({'status': msg.get('status')})}\n\n"
                break
    finally:
        stream_hub.unsubscribe(run_id, queue)
