"""Read-only quality workbench DTOs for 187-P1."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ProjectionStateName = Literal["present", "partial", "unknown", "missing", "forbidden"]


class ProjectionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ProjectionStateName
    data: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_state_data(self) -> "ProjectionState":
        if self.state in {"present", "partial"} and self.data is None:
            raise ValueError(f"{self.state} projection requires data")
        if self.state in {"unknown", "missing", "forbidden"} and self.data is not None:
            raise ValueError(f"{self.state} projection cannot carry data")
        return self


class BoundedFailureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["187.1"] = "187.1"
    event_key: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    stage: Literal["extraction", "retrieval", "rerank", "evidence", "answer", "index"]
    reason: Literal[
        "timeout",
        "oom",
        "provider_fallback",
        "malformed_output",
        "partial_index",
        "unknown_provider",
        "acl_filtered",
        "unknown",
    ]
    provider: str | None = Field(default=None, max_length=128)
    file_id: int = Field(gt=0)
    job_id: int = Field(gt=0)
    request_id: str | None = Field(default=None, max_length=128)
    trace_id: str | None = Field(default=None, min_length=32, max_length=64, pattern=r"^[0-9a-f]+$")
    model_version: str | None = Field(default=None, max_length=128)
    occurred_at: datetime
    retryable: bool
    summary: str = Field(max_length=240)


class QualityWorkbenchCorrelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: int = Field(gt=0)
    job_id: int | None = Field(default=None, gt=0)
    trace_id: str | None = Field(default=None, min_length=32, max_length=64, pattern=r"^[0-9a-f]+$")
    query_hash: str | None = Field(default=None, min_length=16, max_length=16, pattern=r"^[0-9a-f]{16}$")
    request_scope_id: str = Field(min_length=1, max_length=64)
    versions: dict[str, str | None] = Field(default_factory=dict)


class QualityWorkbenchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["187.1"] = "187.1"
    correlation: QualityWorkbenchCorrelation
    extraction: ProjectionState
    retrieval: ProjectionState
    evidence: ProjectionState
    answer: ProjectionState
    failures: list[BoundedFailureEvent] = Field(default_factory=list, max_length=50)
    compatibility: dict[str, Any] | None = None
    truncated: bool = False
    truncated_sections: list[str] = Field(default_factory=list, max_length=5)


class QualityWorkbenchTraceOption(BaseModel):
    """A bounded, ACL-filtered trace choice for one extraction job."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=32, max_length=64, pattern=r"^[0-9a-f]+$")
    status: str = Field(min_length=1, max_length=32)
    query_hash: str | None = Field(default=None, min_length=16, max_length=16, pattern=r"^[0-9a-f]{16}$")
    created_at: datetime | None = None
    finished_at: datetime | None = None


class QualityWorkbenchJobOption(BaseModel):
    """A file-scoped extraction job choice; index jobs are intentionally excluded."""

    model_config = ConfigDict(extra="forbid")

    job_id: int = Field(gt=0)
    status: str = Field(min_length=1, max_length=32)
    provider: str | None = Field(default=None, max_length=64)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    traces: list[QualityWorkbenchTraceOption] = Field(default_factory=list, max_length=50)


class QualityWorkbenchOptionsResponse(BaseModel):
    """Options for deterministic file -> extraction job -> trace selection."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["187.1"] = "187.1"
    file_id: int = Field(gt=0)
    jobs: list[QualityWorkbenchJobOption] = Field(default_factory=list, max_length=50)
