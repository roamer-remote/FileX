# Copyright (c) 2026 徐泽宇
"""OKF import/export API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OkfValidateResponse(BaseModel):
    conformant: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    concept_count: int = 0


class OkfImportResponse(BaseModel):
    concepts_created: int = 0
    concepts_updated: int = 0
    index_pages: int = 0
    log_pages: int = 0
    log_entries_imported: int = 0
    warnings: list[str] = Field(default_factory=list)
    folder_id: int | None = None
    batches_committed: int = 0
    dry_run: bool = False
