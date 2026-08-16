# Copyright (c) 2026 徐泽宇
"""049 Phase B T-7: external sync admin API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExternalSyncWorkspaceOption(BaseModel):
    id: int
    name: str
    kind: str


class ExternalSyncSourceCreateRequest(BaseModel):
    workspace_id: int
    provider: str = Field(default="notion", max_length=32)
    secret: str = Field(min_length=1, max_length=4096)
    config_public_json: dict[str, Any] = Field(default_factory=dict)
    delete_policy: str = Field(default="keep_file", max_length=32)
    is_active: bool = True


class ExternalSyncSourceUpdateRequest(BaseModel):
    workspace_id: int | None = None
    config_public_json: dict[str, Any] | None = None
    delete_policy: str | None = None
    is_active: bool | None = None


class ExternalSyncSourceResponse(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    provider: str
    is_active: bool
    delete_policy: str
    config_public_json: dict[str, Any]
    secret_preview: str
    last_sync_at: str | None
    created_at: str | None
    updated_at: str | None


class ExternalSyncRotateSecretRequest(BaseModel):
    secret: str = Field(min_length=1, max_length=4096)


class ExternalSyncTestConnectionResponse(BaseModel):
    ok: bool
    database_id: str
    title: str | None = None


class ExternalSyncSyncNowResponse(BaseModel):
    run_id: str
    status: str = "accepted"
