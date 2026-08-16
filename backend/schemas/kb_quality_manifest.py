# Copyright (c) 2026 徐泽宇
"""187 extraction manifest DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ManifestStatus = Literal["done", "error", "skip", "defer"]


class ExtractionManifest(BaseModel):
    """A bounded, read-only projection of one extraction job's terminal logs."""

    schema_version: Literal["187.1"] = "187.1"
    file_id: int
    job_id: int
    status: ManifestStatus
    status_reason: str | None = None
    provider: str | None = None
    engine: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    degradation_reason: str | None = None
    provider_version: str | None = None
    source_version: str | None = None
    ocr: dict[str, str] = Field(default_factory=dict)
    manifest_truncated: bool = False
