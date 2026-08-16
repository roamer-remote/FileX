# Copyright (c) 2026 徐泽宇
"""user_setting 相关 API 数据模式模块。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserPreferencesResponse(BaseModel):
    effective: dict[str, bool | int | float | str]
    overrides: dict[str, str]
    inherited_keys: list[str]


class UserPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag_graph_enabled: bool | None = None
    tag_graph_single_node_symbol_size: int | None = Field(default=None, ge=8, le=160)
    tag_graph_node_display_ratio: float | None = Field(default=None, ge=0.1, le=5.0)
    tag_graph_edge_line_width: int | None = Field(default=None, ge=1, le=12)
    kb_extract_provider: str | None = None
    kb_chunk_profile: str | None = None
    kb_index_max_attempts: int | None = Field(default=None, ge=1, le=10)
    kb_voice_notify_enabled: bool | None = None
    kb_voice_notify_playback_ttl_seconds: int | None = Field(default=None, ge=1, le=3600)
    kb_search_hybrid_enabled: bool | None = None
    kb_fts_config: str | None = None
    kb_search_min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    kb_search_boost_keyword_bonus: float | None = Field(default=None, ge=0.0, le=0.5)
    kb_search_mmr_lambda: float | None = Field(default=None, ge=0.0, le=1.0)
    kb_search_filename_boost: float | None = Field(default=None, ge=0.0, le=0.5)
    kb_search_modality_boost_enabled: bool | None = None
    kb_search_modality_boost: float | None = Field(default=None, ge=0.0, le=0.5)
    kb_search_default_top_k: int | None = Field(default=None, ge=5, le=50)
    kb_wiki_compile_min_sources: int | None = Field(default=None, ge=1, le=20)


class UserPreferencesResetRequest(BaseModel):
    keys: list[str] | None = None
