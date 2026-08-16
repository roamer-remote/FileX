"""Versioned failure telemetry contract for 187-P1."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


FailureStage = Literal["extraction", "retrieval", "rerank", "evidence", "answer", "index"]
FailureReason = Literal[
    "timeout",
    "oom",
    "provider_fallback",
    "malformed_output",
    "partial_index",
    "unknown_provider",
    "acl_filtered",
    "unknown",
]


class RagQualityFailureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["187.1"] = "187.1"
    event_key: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    stage: FailureStage
    reason: FailureReason
    provider: str | None = Field(default=None, max_length=128)
    file_id: int = Field(gt=0)
    job_id: int = Field(gt=0)
    request_id: str | None = Field(default=None, max_length=128)
    trace_id: str | None = Field(default=None, min_length=32, max_length=64, pattern=r"^[0-9a-f]+$")
    model_version: str | None = Field(default=None, max_length=128)
    occurred_at: datetime
    retryable: bool
    summary: str = Field(max_length=240)

    @model_validator(mode="after")
    def validate_event_key(self) -> "RagQualityFailureEvent":
        raw = "|".join(
            [
                self.schema_version,
                self.stage,
                self.reason,
                str(self.file_id),
                str(self.job_id),
                self.request_id or "",
                self.trace_id or "",
            ]
        )
        expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        if self.event_key != expected:
            raise ValueError("event_key does not match event identity")
        return self
