# Copyright (c) 2026 徐泽宇
"""system_setting 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from pydantic import BaseModel, Field, field_validator


class ClientSettingsResponse(BaseModel):
    """Web 客户端可见的系统参数（最小暴露面）。"""

    clipboard_prefix: str = ""
    clipboard_suffix: str = ""
    tag_graph_single_node_symbol_size: int = 48
    tag_graph_node_display_ratio: float = 1.0
    tag_graph_edge_line_width: int = 1
    tag_graph_enabled: bool = True
    max_upload_size_mb: int = 10
    shared_workspaces_enabled: bool = True
    kb_extract_provider: str = "legacy"
    kb_search_default_top_k: int = 8
    kb_voice_notify_enabled: bool = True
    kb_voice_notify_playback_ttl_seconds: int = 120
    kb_sag_event_extract_enabled: bool = False
    kb_extract_insavlo_ready: bool = False
    kb_ingestion_pipeline_json: str = ""

    @field_validator("shared_workspaces_enabled", mode="before")
    @classmethod
    def _coerce_client_shared_workspaces_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("tag_graph_enabled", mode="before")
    @classmethod
    def _coerce_client_tag_graph_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_voice_notify_enabled", mode="before")
    @classmethod
    def _coerce_client_kb_voice_notify_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_sag_event_extract_enabled", mode="before")
    @classmethod
    def _coerce_client_kb_sag_event_extract_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")


class SystemSettingsResponse(BaseModel):
    """system设置响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            clipboard_prefix: clipboard前缀（str）。
            clipboard_suffix: clipboardsuffix（str）。
            tag_graph_single_node_symbol_size: 标签图singlenodesymbol大小（int）。
            tag_graph_node_display_ratio: 标签图nodedisplayratio（float）。
            tag_graph_edge_line_width: 标签图edgelinewidth（int）。
            tag_graph_enabled: 标签图启用（bool）。
            max_upload_size_mb: 最大上传大小mb（int）。
            kb_index_max_attempts: 资料库索引最大attempts（int）。
            shared_workspaces_enabled: 共享workspaces启用（bool）。
            kb_search_hybrid_enabled: 资料库检索混合启用（bool）。
            kb_chunk_profile: 资料库分块配置（str）。
    """
    clipboard_prefix: str = ""
    clipboard_suffix: str = ""
    tag_graph_single_node_symbol_size: int = 48
    tag_graph_node_display_ratio: float = 1.0
    tag_graph_edge_line_width: int = 1
    tag_graph_enabled: bool = True
    max_upload_size_mb: int = 10
    workspace_backup_max_mb: int = 100
    kb_index_max_attempts: int = 3
    kb_post_async_enabled: bool = True
    kb_post_max_attempts: int = 3
    agent_run_retention_days: int = 30
    shared_workspaces_enabled: bool = True
    enterprise_rbac_enabled: bool = False
    enterprise_rbac_write_mode: str = "dual"
    enterprise_rbac_cutover: bool = False
    kb_search_hybrid_enabled: bool = False
    kb_chunk_profile: str = "default"
    kb_chunk_size: int | None = None
    kb_chunk_overlap: int | None = None
    kb_chunk_split_recursive: bool = False
    kb_embed_cache_enabled: bool = True
    kb_embed_effective_max_chars: int = 8192
    # T-4 大文档自适应分块阈值
    kb_large_doc_char_threshold: int = 400000
    kb_large_doc_chunk_size: int = 1800
    kb_large_doc_chunk_overlap: int = 150
    kb_raptor_enabled: bool = False
    kb_raptor_min_chars: int = 30000
    kb_large_doc_post_enabled: bool = False
    kb_large_doc_raptor_enabled: bool = False
    kb_ragas_online_eval_enabled: bool = False
    kb_ragas_online_eval_sample_rate: float = 1.0
    kb_ragas_online_eval_timeout_seconds: float = 600.0
    kb_ragas_llm_provider: str = "ollama"
    kb_ragas_llm_base_url: str = ""
    kb_ragas_llm_api_key: str = ""
    kb_ragas_llm_has_api_key: bool = False
    kb_ragas_llm_model: str = ""
    kb_ragas_llm_timeout_seconds: int = 90
    kb_ragas_eval_concurrency: int = 1
    kb_ragas_eval_context_max_count: int = 8
    kb_ragas_eval_context_max_chars_per_item: int = 1200
    kb_ragas_eval_context_max_total_chars: int = 10000
    kb_extract_provider: str = "legacy"
    kb_pdf_inspector_enabled: bool = False
    kb_ingestion_pipeline_json: str = ""
    builtin_routes: list[dict[str, object]] = Field(default_factory=list)
    kb_search_min_score: float = 0.35
    kb_search_boost_keyword_bonus: float = 0.12
    kb_search_mmr_lambda: float = 0.7
    kb_search_filename_boost: float = 0.20
    kb_search_modality_boost: float = 0.15
    kb_search_modality_boost_enabled: bool = False
    kb_fts_config: str = "zh_cn"
    kb_wiki_lint_interval_hours: int = 0
    kb_wiki_compile_min_sources: int = 2
    kb_search_default_top_k: int = 8
    kb_voice_notify_enabled: bool = True
    kb_voice_notify_playback_ttl_seconds: int = 120
    kb_extract_insavlo_enabled: bool = False
    kb_extract_insavlo_base_url: str = "https://demo.insavlo.com/insavlo/public-api"
    kb_extract_insavlo_skill_code: str = ""
    kb_extract_insavlo_callback_origin: str = ""
    kb_extract_insavlo_timeout_minutes: int = 120
    kb_extract_insavlo_api_key: str = ""
    kb_extract_insavlo_has_api_key: bool = False
    kb_extract_insavlo_webhook_secret: str = ""
    kb_extract_insavlo_has_webhook_secret: bool = False
    kb_extract_insavlo_ready: bool = False
    ollama_base_url: str = "http://filex-ollama:11434"
    ollama_embed_model: str = "bge-m3:latest"
    ollama_embed_dim: int = 1024
    ollama_chat_model: str = "qwen3.5:cloud"
    ollama_timeout_sec: float = 120.0
    ollama_embed_batch_size: int = 8
    # Ollama 服务端并行度（重启 filex-ollama 生效）
    ollama_num_parallel: int = 4
    # kb-indexer 客户端 embedding 并发
    ollama_embed_concurrency: int = 4
    ollama_api_key: str = ""
    ollama_has_api_key: bool = False
    kb_post_llm_provider: str = "ollama"
    kb_post_llm_base_url: str = ""
    # 管理员系统设置接口回显已保存的后处理 LLM 凭证；操作日志仍必须脱敏。
    kb_post_llm_api_key: str = ""
    kb_post_llm_has_api_key: bool = False
    kb_post_llm_model: str = ""
    kb_post_llm_timeout_sec: float = 60.0
    kb_post_llm_json_mode: str = "auto"
    mineru_min_batch_mode: str = "auto"
    mineru_min_batch_inference_size: int = 112
    mineru_min_batch_floor: int = 16
    mineru_parse_method: str = "auto"
    mineru_formula_enable: bool = True
    mineru_table_enable: bool = True
    mineru_parse_timeout_sec: int = 1200
    mineru_rpc_timeout_sec: int = 3600
    mineru_page_chunk_enabled: bool = True
    mineru_page_chunk_threshold: int = 160
    mineru_page_chunk_pages: int = 64
    mineru_table_auto_rotate: bool = False
    mineru_table_rotate_max_tables: int = 8
    mineru_table_rotate_timeout_sec: int = 30
    agent_skill_install_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    kb_sag_event_extract_enabled: bool = False
    # 154: 146 P2 多表征增强 master switch（管理员可显式开启；默认 false 维持 146 P-146-01 向后兼容）
    kb_multi_repr_enabled: bool = False
    kb_sag_event_extract_mode: str = "rule"
    kb_sag_event_prompt_version: int = 1
    kb_sag_event_embed_enabled: bool = False
    kb_sag_query_llm_enabled: bool = False

    @field_validator("shared_workspaces_enabled", mode="before")
    @classmethod
    def _coerce_shared_workspaces_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("enterprise_rbac_enabled", mode="before")
    @classmethod
    def _coerce_enterprise_rbac_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("enterprise_rbac_cutover", mode="before")
    @classmethod
    def _coerce_enterprise_rbac_cutover(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_search_hybrid_enabled", mode="before")
    @classmethod
    def _coerce_kb_search_hybrid_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("tag_graph_enabled", mode="before")
    @classmethod
    def _coerce_tag_graph_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_voice_notify_enabled", mode="before")
    @classmethod
    def _coerce_kb_voice_notify_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_chunk_size", "kb_chunk_overlap", mode="before")
    @classmethod
    def _coerce_optional_kb_chunk_int(cls, v: object) -> int | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return int(s)

    @field_validator("kb_chunk_split_recursive", mode="before")
    @classmethod
    def _coerce_kb_chunk_split_recursive(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_embed_cache_enabled", mode="before")
    @classmethod
    def _coerce_kb_embed_cache_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_raptor_enabled", mode="before")
    @classmethod
    def _coerce_kb_raptor_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_post_async_enabled", mode="before")
    @classmethod
    def _coerce_kb_post_async_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_post_max_attempts", mode="before")
    @classmethod
    def _coerce_kb_post_max_attempts(cls, v: object) -> int:
        if isinstance(v, int):
            return v
        return int(str(v).strip() or "3")

    @field_validator("kb_raptor_min_chars", mode="before")
    @classmethod
    def _coerce_kb_raptor_min_chars(cls, v: object) -> int:
        if isinstance(v, int):
            return v
        return int(str(v).strip() or "30000")

    @field_validator("kb_large_doc_post_enabled", "kb_large_doc_raptor_enabled", mode="before")
    @classmethod
    def _coerce_kb_large_doc_post_flags(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_ragas_online_eval_enabled", mode="before")
    @classmethod
    def _coerce_kb_ragas_online_eval_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_embed_effective_max_chars", mode="before")
    @classmethod
    def _coerce_kb_embed_effective_max_chars(cls, v: object) -> int:
        if isinstance(v, int):
            return v
        return int(str(v).strip() or "8192")

    @field_validator("kb_sag_event_extract_enabled", mode="before")
    @classmethod
    def _coerce_kb_sag_event_extract_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_sag_event_embed_enabled", mode="before")
    @classmethod
    def _coerce_kb_sag_event_embed_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_sag_query_llm_enabled", mode="before")
    @classmethod
    def _coerce_kb_sag_query_llm_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_multi_repr_enabled", mode="before")
    @classmethod
    def _coerce_kb_multi_repr_enabled(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_post_llm_has_api_key", mode="before")
    @classmethod
    def _coerce_kb_post_llm_has_api_key(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_ragas_llm_has_api_key", mode="before")
    @classmethod
    def _coerce_kb_ragas_llm_has_api_key(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("kb_sag_event_prompt_version", mode="before")
    @classmethod
    def _coerce_kb_sag_event_prompt_version(cls, v: object) -> int:
        if isinstance(v, int):
            return v
        return int(str(v).strip() or "1")

    @field_validator(
        "mineru_formula_enable",
        "mineru_table_enable",
        "mineru_page_chunk_enabled",
        "mineru_table_auto_rotate",
        mode="before",
    )
    @classmethod
    def _coerce_mineru_bool_fields(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on")


class SystemSettingsUpdate(BaseModel):
    """system设置更新 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-06-09

        Attributes:
            clipboard_prefix: clipboard前缀（str | None）。
            clipboard_suffix: clipboardsuffix（str | None）。
            tag_graph_single_node_symbol_size: 标签图singlenodesymbol大小（int | None）。
            tag_graph_node_display_ratio: 标签图nodedisplayratio（float | None）。
            tag_graph_edge_line_width: 标签图edgelinewidth（int | None）。
            tag_graph_enabled: 标签图启用（bool | None）。
            max_upload_size_mb: 最大上传大小mb（int | None）。
            kb_index_max_attempts: 资料库索引最大attempts（int | None）。
            shared_workspaces_enabled: 共享workspaces启用（bool | None）。
            kb_search_hybrid_enabled: 资料库检索混合启用（bool | None）。
            kb_chunk_profile: 资料库分块配置（str | None）。
    """
    clipboard_prefix: str | None = Field(default=None, max_length=16384)
    clipboard_suffix: str | None = Field(default=None, max_length=16384)
    tag_graph_single_node_symbol_size: int | None = Field(default=None, ge=8, le=160)
    tag_graph_node_display_ratio: float | None = Field(default=None, ge=0.1, le=5.0)
    tag_graph_edge_line_width: int | None = Field(default=None, ge=1, le=12)
    tag_graph_enabled: bool | None = None
    max_upload_size_mb: int | None = Field(default=None, ge=1, le=10240)
    workspace_backup_max_mb: int | None = Field(default=None, ge=1, le=10240)
    kb_index_max_attempts: int | None = Field(default=None, ge=1, le=10)
    kb_post_async_enabled: bool | None = None
    kb_post_max_attempts: int | None = Field(default=None, ge=1, le=10)
    agent_run_retention_days: int | None = Field(default=None, ge=1, le=365)
    shared_workspaces_enabled: bool | None = None
    enterprise_rbac_enabled: bool | None = None
    enterprise_rbac_write_mode: str | None = None
    enterprise_rbac_cutover: bool | None = None
    kb_search_hybrid_enabled: bool | None = None
    kb_chunk_profile: str | None = None
    kb_chunk_size: int | None = Field(default=None, ge=1, le=100000)
    kb_chunk_overlap: int | None = Field(default=None, ge=0, le=99999)
    kb_chunk_split_recursive: bool | None = None
    kb_embed_cache_enabled: bool | None = None
    kb_extract_provider: str | None = None
    kb_pdf_inspector_enabled: bool | None = None
    kb_ingestion_pipeline_json: str | None = None
    kb_search_min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    kb_search_boost_keyword_bonus: float | None = Field(default=None, ge=0.0, le=0.5)
    kb_search_mmr_lambda: float | None = Field(default=None, ge=0.0, le=1.0)
    kb_search_filename_boost: float | None = Field(default=None, ge=0.0, le=0.5)
    kb_search_modality_boost: float | None = Field(default=None, ge=0.0, le=0.5)
    kb_search_modality_boost_enabled: bool | None = None
    kb_fts_config: str | None = None
    kb_wiki_lint_interval_hours: int | None = Field(default=None, ge=0, le=168)
    kb_wiki_compile_min_sources: int | None = Field(default=None, ge=1, le=20)
    kb_search_default_top_k: int | None = Field(default=None, ge=5, le=50)
    kb_voice_notify_enabled: bool | None = None
    kb_voice_notify_playback_ttl_seconds: int | None = Field(default=None, ge=1, le=3600)
    # 154: 146 P2 多表征增强 master switch
    kb_multi_repr_enabled: bool | None = None
    kb_extract_insavlo_enabled: bool | None = None
    kb_extract_insavlo_base_url: str | None = None
    kb_extract_insavlo_api_key: str | None = None
    kb_extract_insavlo_webhook_secret: str | None = None
    kb_extract_insavlo_skill_code: str | None = None
    kb_extract_insavlo_callback_origin: str | None = None
    kb_extract_insavlo_timeout_minutes: int | None = Field(default=None, ge=2, le=120)
    clear_insavlo_api_key: bool | None = None
    clear_insavlo_webhook_secret: bool | None = None
    ollama_base_url: str | None = None
    ollama_embed_model: str | None = None
    ollama_embed_dim: int | None = Field(default=None, ge=128, le=4096)
    ollama_chat_model: str | None = None
    ollama_timeout_sec: float | None = Field(default=None, ge=10, le=600)
    ollama_embed_batch_size: int | None = Field(default=None, ge=1, le=64)
    # 服务端并行（重启 ollama 容器后生效）
    ollama_num_parallel: int | None = Field(default=None, ge=1, le=32)
    # 客户端并发（新任务立即生效）
    ollama_embed_concurrency: int | None = Field(default=None, ge=1, le=32)
    ollama_api_key: str | None = None
    clear_ollama_api_key: bool | None = None
    kb_post_llm_provider: str | None = None
    kb_post_llm_base_url: str | None = None
    kb_post_llm_api_key: str | None = None
    kb_post_llm_model: str | None = None
    kb_post_llm_timeout_sec: float | None = Field(default=None, ge=5, le=300)
    kb_post_llm_json_mode: str | None = None
    clear_kb_post_llm_api_key: bool | None = None
    # T-4 大文档阈值（允许客户端 patch）
    kb_large_doc_char_threshold: int | None = Field(default=None, ge=10000, le=10000000)
    kb_large_doc_chunk_size: int | None = Field(default=None, ge=200, le=8000)
    kb_large_doc_chunk_overlap: int | None = Field(default=None, ge=0, le=2000)
    kb_raptor_enabled: bool | None = None
    kb_large_doc_post_enabled: bool | None = None
    kb_large_doc_raptor_enabled: bool | None = None
    kb_ragas_online_eval_enabled: bool | None = None
    kb_ragas_online_eval_sample_rate: float | None = None
    kb_ragas_online_eval_timeout_seconds: float | None = Field(default=None, ge=1, le=3000)
    kb_ragas_llm_provider: str | None = None
    kb_ragas_llm_base_url: str | None = None
    kb_ragas_llm_api_key: str | None = None
    kb_ragas_llm_model: str | None = None
    kb_ragas_llm_timeout_seconds: int | None = Field(default=None, ge=10, le=300)
    kb_ragas_eval_concurrency: int | None = Field(default=None, ge=1, le=4)
    kb_ragas_eval_context_max_count: int | None = Field(default=None, ge=1, le=20)
    kb_ragas_eval_context_max_chars_per_item: int | None = Field(default=None, ge=200, le=4000)
    kb_ragas_eval_context_max_total_chars: int | None = Field(default=None, ge=1000, le=40000)
    clear_kb_ragas_llm_api_key: bool | None = None
    mineru_min_batch_mode: str | None = None
    mineru_min_batch_inference_size: int | None = Field(default=None, ge=8, le=384)
    mineru_min_batch_floor: int | None = Field(default=None, ge=8, le=384)
    mineru_parse_method: str | None = None
    mineru_formula_enable: bool | None = None
    mineru_table_enable: bool | None = None
    mineru_parse_timeout_sec: int | None = Field(default=None, ge=60, le=3600)
    mineru_rpc_timeout_sec: int | None = Field(default=None, ge=60, le=7200)
    mineru_page_chunk_enabled: bool | None = None
    mineru_page_chunk_threshold: int | None = Field(default=None, ge=1, le=2000)
    mineru_page_chunk_pages: int | None = Field(default=None, ge=8, le=200)
    mineru_table_auto_rotate: bool | None = None
    mineru_table_rotate_max_tables: int | None = Field(default=None, ge=1, le=64)
    mineru_table_rotate_timeout_sec: int | None = Field(default=None, ge=1, le=300)
    agent_skill_install_prompt: str | None = Field(default=None, max_length=65536)
    kb_sag_event_extract_enabled: bool | None = None
    kb_sag_event_extract_mode: str | None = None
    kb_sag_event_prompt_version: int | None = None
    kb_sag_event_embed_enabled: bool | None = None
    kb_sag_query_llm_enabled: bool | None = None
