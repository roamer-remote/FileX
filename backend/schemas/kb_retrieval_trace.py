# Copyright (c) 2026 徐泽宇
"""187 bounded retrieval trace DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RetrievalTrace(BaseModel):
    schema_version: Literal["187.1"] = "187.1"
    trace_id: str = Field(..., min_length=1, max_length=64)
    request_scope: str = Field(..., min_length=1, max_length=64)
    user_id: int | None = None
    workspace_id: int | None = None
    agent_run_id: str | None = Field(default=None, max_length=64)
    job_id: int | None = Field(default=None, gt=0)
    status: str = Field(default="completed", min_length=1, max_length=32)
    finished_at: datetime | None = None
    query_normalized: str = Field(default="", max_length=256)
    counts: dict[str, int] = Field(default_factory=dict)
    final_file_ids: list[int] = Field(default_factory=list, max_length=100)
    final_chunk_ids: list[int] = Field(default_factory=list, max_length=100)
    expansion_ids: list[int] = Field(default_factory=list, max_length=100)
    expansion_summary: dict[str, Any] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    cache_hit: bool | None = None
    fallback_mode: str | None = Field(default=None, max_length=64)
    fallback_reason: str | None = Field(default=None, max_length=128)
    compatibility: dict[str, Any] = Field(default_factory=dict)
    truncated: bool = False
