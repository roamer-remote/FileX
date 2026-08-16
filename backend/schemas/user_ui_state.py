# Copyright (c) 2026 徐泽宇
"""039 user_ui_state API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

FolderSelection = Union[Literal["all", "uncategorized"], int]


class PanelPos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int


class PanelSize(BaseModel):
    model_config = ConfigDict(extra="forbid")

    w: int
    h: int


class MqPetPos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int


class FoldersState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_by_ws: dict[str, FolderSelection] = Field(default_factory=dict)
    expanded_by_ws: dict[str, list[int]] = Field(default_factory=dict)
    panel_visible_by_ws: dict[str, bool] = Field(default_factory=dict)
    panel_pos_by_ws: dict[str, PanelPos] = Field(default_factory=dict)
    panel_size_by_ws: dict[str, PanelSize] = Field(default_factory=dict)


class SidebarState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collapsed: bool = False
    groups: dict[str, str] = Field(default_factory=dict)


class ThemeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["light", "dark", "system"] = "system"
    accent: Literal["blue"] = "blue"

    @field_validator("accent", mode="before")
    @classmethod
    def normalize_accent(cls, v: Any) -> str:
        return "blue" if v != "blue" else v


class LoginPrefs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auth_method: Literal["password", "wechat"] = "password"
    remember_me: bool = False


class KbEvalState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cross_workspace: bool = False
    filename_boost: bool = True
    modality_boost: bool = False
    hybrid: bool | None = None
    query_expansion: bool = False
    evidence_mode: Literal["chunk", "monte_carlo"] = "chunk"


class MqPetState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pos: MqPetPos | None = None


class KbToolbarState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pos: MqPetPos | None = None
    collapsed: bool = False


class AdminOrgState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_tab: Literal["departments", "groups"] = "departments"
    selected_department_id: int | None = None
    expanded_department_ids: list[int] = Field(default_factory=list)


class KbIndexState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_tab: Literal["preview", "rebuild", "okf"] = "preview"
    preview_sub_tab: Literal["auto", "wikiPages", "wiki", "linkGraph"] = "auto"


class UserUiStateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: Literal[1] = 1
    active_workspace_id: int | None = None
    getting_started_seen: bool = False
    folders: FoldersState = Field(default_factory=FoldersState)
    sidebar: SidebarState = Field(default_factory=SidebarState)
    theme: ThemeState = Field(default_factory=ThemeState)
    locale: Literal["zh-CN", "en"] = "zh-CN"
    login: LoginPrefs = Field(default_factory=LoginPrefs)
    kb_eval: KbEvalState = Field(default_factory=KbEvalState)
    mq_pet: MqPetState = Field(default_factory=MqPetState)
    kb_toolbar: KbToolbarState = Field(default_factory=KbToolbarState)
    admin_org: AdminOrgState = Field(default_factory=AdminOrgState)
    kb_index: KbIndexState = Field(default_factory=KbIndexState)


class UiStateResponse(BaseModel):
    state: UserUiStateV1
    updated_at: datetime | None = None


class UiStatePatch(BaseModel):
    """PUT body：字段 optional；嵌套对象允许 partial，由 service deep_merge。"""

    model_config = ConfigDict(extra="forbid")

    v: Literal[1] | None = None
    active_workspace_id: int | None = None
    getting_started_seen: bool | None = None
    folders: dict[str, Any] | None = None
    sidebar: dict[str, Any] | None = None
    theme: dict[str, Any] | None = None
    locale: Literal["zh-CN", "en"] | None = None
    login: dict[str, Any] | None = None
    kb_eval: dict[str, Any] | None = None
    mq_pet: dict[str, Any] | None = None
    kb_toolbar: dict[str, Any] | None = None
    admin_org: dict[str, Any] | None = None
    kb_index: dict[str, Any] | None = None
