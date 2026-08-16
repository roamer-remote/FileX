# Copyright (c) 2026 徐泽宇
"""Shared types for external sync runners."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExternalPagePayload:
    external_key: str
    title: str
    markdown: str
    external_uri: str | None
    external_updated_at: datetime


@dataclass
class UpsertExternalPageResult:
    file_id: int
    item_id: int
    created_file: bool
    content_changed: bool
    index_job_id: int | None
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class NotionSyncStats:
    pages_seen: int = 0
    upserted: int = 0
    unchanged: int = 0
    deleted_remote: int = 0
    skipped: int = 0
    index_jobs: int = 0
