# Copyright (c) 2026 徐泽宇
"""107 agent run trace API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentRunStatus = Literal["running", "completed", "failed", "cancelled"]
EventLayer = Literal["router", "kb", "tool"]
EventPhase = Literal["start", "end", "error", "skip"]


class AgentRunCreateRequest(BaseModel):
    thread_id: str | None = None
    question_preview: str = ""
    intent: str | None = None


class AgentRunCreateResponse(BaseModel):
    run_id: str
    view_url: str


class AgentRunEnsureResponse(BaseModel):
    run_id: str
    view_url: str
    created: bool


class AgentRunEventIn(BaseModel):
    client_event_id: str | None = None
    parent_client_event_id: str | None = None
    task_key: str | None = None
    span_id: str | None = None
    attempt: int = 1
    ts: datetime | None = None
    layer: EventLayer
    node_id: str
    label: str
    phase: EventPhase
    duration_ms: int | None = None
    meta: dict[str, Any] | None = None


class AgentRunEventsBatchRequest(BaseModel):
    events: list[AgentRunEventIn] = Field(default_factory=list, max_length=100)


class AgentRunEventAssigned(BaseModel):
    client_event_id: str | None = None
    seq: int


class AgentRunEventsBatchResponse(BaseModel):
    assigned: list[AgentRunEventAssigned]


class AgentRunPatchRequest(BaseModel):
    status: AgentRunStatus
    summary_json: dict[str, Any] | None = None
    duration_ms: int | None = None


class AgentRunEventOut(BaseModel):
    seq: int
    client_event_id: str | None = None
    parent_seq: int | None = None
    task_key: str | None = None
    span_id: str | None = None
    attempt: int
    ts: datetime
    layer: str
    node_id: str
    label: str
    phase: str
    duration_ms: int | None = None
    meta_json: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class AgentRunSummary(BaseModel):
    id: str
    thread_id: str | None = None
    question_preview: str
    intent: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    summary_json: dict[str, Any] | None = None
    username: str | None = None

    model_config = {"from_attributes": True}


class AgentRunListResponse(BaseModel):
    total: int
    items: list[AgentRunSummary]


class AgentRunDetailResponse(AgentRunSummary):
    events: list[AgentRunEventOut]


class AgentRunEventsDeltaResponse(BaseModel):
    events: list[AgentRunEventOut]
    run_status: str
    latest_seq: int


class AgentRunDeleteRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1, max_length=100)


class AgentRunDeleteResponse(BaseModel):
    deleted: int
