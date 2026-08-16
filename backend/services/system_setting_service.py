# Copyright (c) 2026 徐泽宇
"""system_setting_service 业务逻辑模块。

Authors:
    徐泽宇
"""

import threading
from dataclasses import dataclass

from sqlalchemy.orm import Session

from config import KB_EXTRACT_MINERU_TIMEOUT_SEC, KB_SEARCH_BOOST_KEYWORD_BONUS, KB_SEARCH_FILENAME_BOOST, KB_SEARCH_MIN_SCORE, KB_SEARCH_MODALITY_BOOST, KB_SEARCH_MMR_LAMBDA, KB_SEARCH_TOP_K_DEFAULT, KB_SEARCH_TOP_K_MAX, OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, OLLAMA_EMBED_BATCH_SIZE, OLLAMA_EMBED_DIM, OLLAMA_EMBED_MODEL, OLLAMA_TIMEOUT_SEC, TAG_COOC_MIN_EDGE_DEFAULT
from models.system_setting import SystemSetting

_cache_lock = threading.Lock()
"""进程内缓存（多 worker 下各进程独立；管理员保存后会失效并刷新）。"""
_settings_cache: dict[str, str] | None = None

KEY_CLIPBOARD_PREFIX = "clipboard_prefix"
KEY_CLIPBOARD_SUFFIX = "clipboard_suffix"
KEY_TAG_GRAPH_SINGLE = "tag_graph_single_node_symbol_size"
KEY_TAG_GRAPH_NODE_DISPLAY_RATIO = "tag_graph_node_display_ratio"
KEY_TAG_GRAPH_EDGE_LINE_WIDTH = "tag_graph_edge_line_width"
KEY_TAG_GRAPH_ENABLED = "tag_graph_enabled"
KEY_MAX_UPLOAD_SIZE_MB = "max_upload_size_mb"
KEY_WORKSPACE_BACKUP_MAX_MB = "workspace_backup_max_mb"
KEY_KB_INDEX_MAX_ATTEMPTS = "kb_index_max_attempts"
KEY_KB_POST_ASYNC_ENABLED = "kb_post_async_enabled"
KEY_KB_POST_MAX_ATTEMPTS = "kb_post_max_attempts"
KEY_AGENT_RUN_RETENTION_DAYS = "agent_run_retention_days"
KEY_SHARED_WORKSPACES_ENABLED = "shared_workspaces_enabled"
KEY_ENTERPRISE_RBAC_ENABLED = "enterprise_rbac_enabled"
KEY_ENTERPRISE_RBAC_WRITE_MODE = "enterprise_rbac_write_mode"
KEY_ENTERPRISE_RBAC_CUTOVER = "enterprise_rbac_cutover"
KEY_KB_SEARCH_HYBRID_ENABLED = "kb_search_hybrid_enabled"
KEY_KB_SEARCH_TAG_COOC_ENABLED = "kb_search_tag_cooc_enabled"
KEY_KB_SEARCH_TAG_COOC_MIN_EDGE = "kb_search_tag_cooc_min_edge"
KEY_KB_CHUNK_PROFILE = "kb_chunk_profile"
KEY_KB_CHUNK_SIZE = "kb_chunk_size"
KEY_KB_CHUNK_OVERLAP = "kb_chunk_overlap"
KEY_KB_CHUNK_SPLIT_RECURSIVE = "kb_chunk_split_recursive"
KEY_KB_EMBED_CACHE_ENABLED = "kb_embed_cache_enabled"
KEY_KB_EXTRACT_PROVIDER = "kb_extract_provider"
KEY_KB_PDF_INSPECTOR_ENABLED = "kb_pdf_inspector_enabled"
KEY_KB_SEARCH_MIN_SCORE = "kb_search_min_score"
KEY_KB_SEARCH_BOOST_KEYWORD_BONUS = "kb_search_boost_keyword_bonus"
KEY_KB_SEARCH_MMR_LAMBDA = "kb_search_mmr_lambda"
KEY_KB_SEARCH_FILENAME_BOOST = "kb_search_filename_boost"
KEY_KB_SEARCH_MODALITY_BOOST = "kb_search_modality_boost"
KEY_KB_SEARCH_MODALITY_BOOST_ENABLED = "kb_search_modality_boost_enabled"
KEY_KB_SEARCH_DEFAULT_TOP_K = "kb_search_default_top_k"
KEY_KB_VOICE_NOTIFY_ENABLED = "kb_voice_notify_enabled"
# 153: voice playback TTL (seconds) — stale browser speech cleanup window.
KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS = "kb_voice_notify_playback_ttl_seconds"
KEY_KB_FTS_CONFIG = "kb_fts_config"
KEY_KB_WIKI_LINT_INTERVAL_HOURS = "kb_wiki_lint_interval_hours"
KEY_KB_WIKI_COMPILE_MIN_SOURCES = "kb_wiki_compile_min_sources"
KEY_KB_SEARCH_CACHE_ENABLED = "kb_search_cache_enabled"
KEY_KB_SEARCH_CACHE_SIMILARITY_THRESHOLD = "kb_search_cache_similarity_threshold"
KEY_KB_SEARCH_CACHE_TTL_HOURS = "kb_search_cache_ttl_hours"
KEY_KB_SEARCH_CACHE_MAX_ENTRIES_PER_USER = "kb_search_cache_max_entries_per_user"
KEY_KB_EVIDENCE_LONG_DOC_CHARS = "kb_evidence_long_doc_chars"
KEY_KB_EVIDENCE_SAMPLE_K_DEFAULT = "kb_evidence_sample_k_default"
KEY_KB_EVIDENCE_MONTE_CARLO_MAX_FILES = "kb_evidence_monte_carlo_max_files"
KEY_KB_ENTITY_EXTRACT_ENABLED = "kb_entity_extract_enabled"
KEY_KB_SAG_EVENT_EXTRACT_ENABLED = "kb_sag_event_extract_enabled"
KEY_KB_SAG_EVENT_EXTRACT_MODE = "kb_sag_event_extract_mode"
KEY_KB_SAG_EVENT_PROMPT_VERSION = "kb_sag_event_prompt_version"
KEY_KB_SAG_EVENT_EMBED_ENABLED = "kb_sag_event_embed_enabled"
KEY_KB_SAG_QUERY_LLM_ENABLED = "kb_sag_query_llm_enabled"
KEY_KB_RAPTOR_ENABLED = "kb_raptor_enabled"
KEY_KB_RAPTOR_MIN_CHARS = "kb_raptor_min_chars"
KEY_KB_RAPTOR_MAX_LEVELS = "kb_raptor_max_levels"
KEY_KB_RAPTOR_MAX_SUMMARIES_PER_FILE = "kb_raptor_max_summaries_per_file"
KEY_KB_RAPTOR_OLLAMA_TIMEOUT_SEC = "kb_raptor_ollama_timeout_sec"
KEY_KB_RAPTOR_FAIL_OPEN = "kb_raptor_fail_open"
KEY_KB_RAPTOR_DRILL_K = "kb_raptor_drill_k"
KEY_KB_RAPTOR_DRILL_SCORE_FACTOR = "kb_raptor_drill_score_factor"
# 154: P2 multi-representation search master switch (146 FR-P2-003)
KEY_KB_MULTI_REPR_ENABLED = "kb_multi_repr_enabled"
KEY_KB_LARGE_DOC_CHAR_THRESHOLD = "kb_large_doc_char_threshold"
KEY_KB_LARGE_DOC_CHUNK_SIZE = "kb_large_doc_chunk_size"
KEY_KB_LARGE_DOC_CHUNK_OVERLAP = "kb_large_doc_chunk_overlap"
# 101: large doc post-processing (entity/sag) even when force=true; default off
KEY_KB_LARGE_DOC_POST_ENABLED = "kb_large_doc_post_enabled"
# 101: large doc RAPTOR even when force=true; default off
KEY_KB_LARGE_DOC_RAPTOR_ENABLED = "kb_large_doc_raptor_enabled"
KEY_KB_EXTRACT_INSAVLO_ENABLED = "kb_extract_insavlo_enabled"
KEY_KB_EXTRACT_INSAVLO_BASE_URL = "kb_extract_insavlo_base_url"
KEY_KB_EXTRACT_INSAVLO_API_KEY = "kb_extract_insavlo_api_key"
KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET = "kb_extract_insavlo_webhook_secret"
KEY_KB_EXTRACT_INSAVLO_SKILL_CODE = "kb_extract_insavlo_skill_code"
KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN = "kb_extract_insavlo_callback_origin"
KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS = "kb_extract_insavlo_timeout_hours"  # legacy(063): migration read only
KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES = "kb_extract_insavlo_timeout_minutes"
KEY_KB_INGESTION_PIPELINE_JSON = "kb_ingestion_pipeline_json"
KEY_OLLAMA_BASE_URL = "ollama_base_url"
KEY_OLLAMA_EMBED_MODEL = "ollama_embed_model"
KEY_OLLAMA_EMBED_DIM = "ollama_embed_dim"
KEY_OLLAMA_CHAT_MODEL = "ollama_chat_model"
KEY_OLLAMA_TIMEOUT_SEC = "ollama_timeout_sec"
KEY_OLLAMA_EMBED_BATCH_SIZE = "ollama_embed_batch_size"
KEY_OLLAMA_NUM_PARALLEL = "ollama_num_parallel"
KEY_OLLAMA_EMBED_CONCURRENCY = "ollama_embed_concurrency"
KEY_OLLAMA_API_KEY = "ollama_api_key"
KEY_KB_POST_LLM_PROVIDER = "kb_post_llm_provider"
KEY_KB_POST_LLM_BASE_URL = "kb_post_llm_base_url"
KEY_KB_POST_LLM_API_KEY = "kb_post_llm_api_key"
KEY_KB_POST_LLM_MODEL = "kb_post_llm_model"
KEY_KB_POST_LLM_TIMEOUT_SEC = "kb_post_llm_timeout_sec"
KEY_KB_POST_LLM_JSON_MODE = "kb_post_llm_json_mode"

KEY_KB_RAGAS_ONLINE_EVAL_ENABLED = "kb_ragas_online_eval_enabled"
KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE = "kb_ragas_online_eval_sample_rate"
KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS = "kb_ragas_online_eval_timeout_seconds"
KEY_KB_RAGAS_LLM_PROVIDER = "kb_ragas_llm_provider"
KEY_KB_RAGAS_LLM_BASE_URL = "kb_ragas_llm_base_url"
KEY_KB_RAGAS_LLM_API_KEY = "kb_ragas_llm_api_key"
KEY_KB_RAGAS_LLM_MODEL = "kb_ragas_llm_model"
KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS = "kb_ragas_llm_timeout_seconds"
KEY_KB_RAGAS_EVAL_CONCURRENCY = "kb_ragas_eval_concurrency"
KEY_KB_RAGAS_EVAL_CONTEXT_MAX_COUNT = "kb_ragas_eval_context_max_count"
KEY_KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM = "kb_ragas_eval_context_max_chars_per_item"
KEY_KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS = "kb_ragas_eval_context_max_total_chars"

KEY_MINERU_MIN_BATCH_MODE = "mineru_min_batch_mode"
KEY_MINERU_MIN_BATCH_INFERENCE_SIZE = "mineru_min_batch_inference_size"
KEY_MINERU_MIN_BATCH_FLOOR = "mineru_min_batch_floor"
KEY_MINERU_PARSE_METHOD = "mineru_parse_method"
KEY_MINERU_FORMULA_ENABLE = "mineru_formula_enable"
KEY_MINERU_TABLE_ENABLE = "mineru_table_enable"
KEY_MINERU_PARSE_TIMEOUT_SEC = "mineru_parse_timeout_sec"
KEY_MINERU_RPC_TIMEOUT_SEC = "mineru_rpc_timeout_sec"
KEY_MINERU_PAGE_CHUNK_ENABLED = "mineru_page_chunk_enabled"
KEY_MINERU_PAGE_CHUNK_THRESHOLD = "mineru_page_chunk_threshold"
KEY_MINERU_PAGE_CHUNK_PAGES = "mineru_page_chunk_pages"
KEY_MINERU_TABLE_AUTO_ROTATE = "mineru_table_auto_rotate"
KEY_MINERU_TABLE_ROTATE_MAX_TABLES = "mineru_table_rotate_max_tables"
KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC = "mineru_table_rotate_timeout_sec"

KEY_AGENT_SKILL_INSTALL_PROMPT = "agent_skill_install_prompt"

MINERU_SETTING_KEYS: tuple[str, ...] = (
    KEY_MINERU_MIN_BATCH_MODE,
    KEY_MINERU_MIN_BATCH_INFERENCE_SIZE,
    KEY_MINERU_MIN_BATCH_FLOOR,
    KEY_MINERU_PARSE_METHOD,
    KEY_MINERU_FORMULA_ENABLE,
    KEY_MINERU_TABLE_ENABLE,
    KEY_MINERU_PARSE_TIMEOUT_SEC,
    KEY_MINERU_RPC_TIMEOUT_SEC,
    KEY_MINERU_PAGE_CHUNK_ENABLED,
    KEY_MINERU_PAGE_CHUNK_THRESHOLD,
    KEY_MINERU_PAGE_CHUNK_PAGES,
    KEY_MINERU_TABLE_AUTO_ROTATE,
    KEY_MINERU_TABLE_ROTATE_MAX_TABLES,
    KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC,
)

KNOWN_KEYS = (
    KEY_CLIPBOARD_PREFIX,
    KEY_CLIPBOARD_SUFFIX,
    KEY_TAG_GRAPH_SINGLE,
    KEY_TAG_GRAPH_NODE_DISPLAY_RATIO,
    KEY_TAG_GRAPH_EDGE_LINE_WIDTH,
    KEY_TAG_GRAPH_ENABLED,
    KEY_MAX_UPLOAD_SIZE_MB,
    KEY_WORKSPACE_BACKUP_MAX_MB,
    KEY_KB_INDEX_MAX_ATTEMPTS,
    KEY_KB_POST_ASYNC_ENABLED,
    KEY_KB_POST_MAX_ATTEMPTS,
    KEY_AGENT_RUN_RETENTION_DAYS,
    KEY_SHARED_WORKSPACES_ENABLED,
    KEY_ENTERPRISE_RBAC_ENABLED,
    KEY_ENTERPRISE_RBAC_WRITE_MODE,
    KEY_ENTERPRISE_RBAC_CUTOVER,
    KEY_KB_SEARCH_HYBRID_ENABLED,
    KEY_KB_SEARCH_TAG_COOC_ENABLED,
    KEY_KB_SEARCH_TAG_COOC_MIN_EDGE,
    KEY_KB_CHUNK_PROFILE,
    KEY_KB_CHUNK_SIZE,
    KEY_KB_CHUNK_OVERLAP,
    KEY_KB_CHUNK_SPLIT_RECURSIVE,
    KEY_KB_EMBED_CACHE_ENABLED,
    KEY_KB_EXTRACT_PROVIDER,
    KEY_KB_PDF_INSPECTOR_ENABLED,
    KEY_KB_SEARCH_MIN_SCORE,
    KEY_KB_SEARCH_BOOST_KEYWORD_BONUS,
    KEY_KB_SEARCH_MMR_LAMBDA,
    KEY_KB_SEARCH_FILENAME_BOOST,
    KEY_KB_SEARCH_MODALITY_BOOST,
    KEY_KB_SEARCH_MODALITY_BOOST_ENABLED,
    KEY_KB_SEARCH_DEFAULT_TOP_K,
    KEY_KB_VOICE_NOTIFY_ENABLED,
    KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS,
    KEY_KB_FTS_CONFIG,
    KEY_KB_WIKI_LINT_INTERVAL_HOURS,
    KEY_KB_WIKI_COMPILE_MIN_SOURCES,
    KEY_KB_SEARCH_CACHE_ENABLED,
    KEY_KB_SEARCH_CACHE_SIMILARITY_THRESHOLD,
    KEY_KB_SEARCH_CACHE_TTL_HOURS,
    KEY_KB_SEARCH_CACHE_MAX_ENTRIES_PER_USER,
    KEY_KB_EVIDENCE_LONG_DOC_CHARS,
    KEY_KB_EVIDENCE_SAMPLE_K_DEFAULT,
    KEY_KB_EVIDENCE_MONTE_CARLO_MAX_FILES,
    KEY_KB_ENTITY_EXTRACT_ENABLED,
    KEY_KB_SAG_EVENT_EXTRACT_ENABLED,
    KEY_KB_SAG_EVENT_EXTRACT_MODE,
    KEY_KB_SAG_EVENT_PROMPT_VERSION,
    KEY_KB_SAG_EVENT_EMBED_ENABLED,
    KEY_KB_SAG_QUERY_LLM_ENABLED,
    KEY_KB_RAPTOR_ENABLED,
    KEY_KB_RAPTOR_MIN_CHARS,
    KEY_KB_RAPTOR_MAX_LEVELS,
    KEY_KB_RAPTOR_MAX_SUMMARIES_PER_FILE,
    KEY_KB_RAPTOR_OLLAMA_TIMEOUT_SEC,
    KEY_KB_RAPTOR_FAIL_OPEN,
    KEY_KB_RAPTOR_DRILL_K,
    KEY_KB_RAPTOR_DRILL_SCORE_FACTOR,
    KEY_KB_MULTI_REPR_ENABLED,
    KEY_KB_EXTRACT_INSAVLO_ENABLED,
    KEY_KB_EXTRACT_INSAVLO_BASE_URL,
    KEY_KB_EXTRACT_INSAVLO_API_KEY,
    KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET,
    KEY_KB_EXTRACT_INSAVLO_SKILL_CODE,
    KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN,
    KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
    KEY_KB_INGESTION_PIPELINE_JSON,
    KEY_OLLAMA_BASE_URL,
    KEY_OLLAMA_EMBED_MODEL,
    KEY_OLLAMA_EMBED_DIM,
    KEY_OLLAMA_CHAT_MODEL,
    KEY_OLLAMA_TIMEOUT_SEC,
    KEY_OLLAMA_EMBED_BATCH_SIZE,
    KEY_OLLAMA_NUM_PARALLEL,
    KEY_OLLAMA_EMBED_CONCURRENCY,
    KEY_OLLAMA_API_KEY,
    KEY_KB_POST_LLM_PROVIDER,
    KEY_KB_POST_LLM_BASE_URL,
    KEY_KB_POST_LLM_API_KEY,
    KEY_KB_POST_LLM_MODEL,
    KEY_KB_POST_LLM_TIMEOUT_SEC,
    KEY_KB_POST_LLM_JSON_MODE,
    KEY_MINERU_MIN_BATCH_MODE,
    KEY_MINERU_MIN_BATCH_INFERENCE_SIZE,
    KEY_MINERU_MIN_BATCH_FLOOR,
    KEY_MINERU_PARSE_METHOD,
    KEY_MINERU_FORMULA_ENABLE,
    KEY_MINERU_TABLE_ENABLE,
    KEY_MINERU_PARSE_TIMEOUT_SEC,
    KEY_MINERU_RPC_TIMEOUT_SEC,
    KEY_MINERU_PAGE_CHUNK_ENABLED,
    KEY_MINERU_PAGE_CHUNK_THRESHOLD,
    KEY_MINERU_PAGE_CHUNK_PAGES,
    KEY_MINERU_TABLE_AUTO_ROTATE,
    KEY_MINERU_TABLE_ROTATE_MAX_TABLES,
    KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC,
    # T-4 large doc adaptive chunking thresholds
    KEY_KB_LARGE_DOC_CHAR_THRESHOLD,
    KEY_KB_LARGE_DOC_CHUNK_SIZE,
    KEY_KB_LARGE_DOC_CHUNK_OVERLAP,
    KEY_KB_LARGE_DOC_POST_ENABLED,
    KEY_KB_LARGE_DOC_RAPTOR_ENABLED,
    KEY_KB_RAGAS_ONLINE_EVAL_ENABLED,
    KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE,
    KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS,
    KEY_KB_RAGAS_LLM_PROVIDER,
    KEY_KB_RAGAS_LLM_BASE_URL,
    KEY_KB_RAGAS_LLM_API_KEY,
    KEY_KB_RAGAS_LLM_MODEL,
    KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS,
    KEY_KB_RAGAS_EVAL_CONCURRENCY,
    KEY_KB_RAGAS_EVAL_CONTEXT_MAX_COUNT,
    KEY_KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM,
    KEY_KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS,
    KEY_AGENT_SKILL_INSTALL_PROMPT,
)


def _workspace_backup_max_mb_env_default() -> str:
    import os

    try:
        b = max(1, int(os.environ.get("WORKSPACE_BACKUP_MAX_BYTES") or "104857600"))
        return str(max(1, b // (1024 * 1024)))
    except ValueError:
        return "100"


DEFAULTS: dict[str, str] = {
    KEY_CLIPBOARD_PREFIX: "",
    KEY_CLIPBOARD_SUFFIX: "",
    KEY_TAG_GRAPH_SINGLE: "48",
    KEY_TAG_GRAPH_NODE_DISPLAY_RATIO: "1.0",
    KEY_TAG_GRAPH_EDGE_LINE_WIDTH: "1",
    KEY_TAG_GRAPH_ENABLED: "true",
    KEY_MAX_UPLOAD_SIZE_MB: "10",
    KEY_WORKSPACE_BACKUP_MAX_MB: _workspace_backup_max_mb_env_default(),
    KEY_KB_INDEX_MAX_ATTEMPTS: "3",
    KEY_KB_POST_ASYNC_ENABLED: "true",
    KEY_KB_POST_MAX_ATTEMPTS: "3",
    KEY_AGENT_RUN_RETENTION_DAYS: "30",
    KEY_SHARED_WORKSPACES_ENABLED: "true",
    KEY_ENTERPRISE_RBAC_ENABLED: "false",
    KEY_ENTERPRISE_RBAC_WRITE_MODE: "dual",
    KEY_ENTERPRISE_RBAC_CUTOVER: "false",
    KEY_KB_SEARCH_HYBRID_ENABLED: "true",
    KEY_KB_SEARCH_TAG_COOC_ENABLED: "true",
    KEY_KB_SEARCH_TAG_COOC_MIN_EDGE: str(TAG_COOC_MIN_EDGE_DEFAULT),
    KEY_KB_CHUNK_PROFILE: "long_doc",
    KEY_KB_CHUNK_SIZE: "",
    KEY_KB_CHUNK_OVERLAP: "",
    KEY_KB_CHUNK_SPLIT_RECURSIVE: "false",
    KEY_KB_EMBED_CACHE_ENABLED: "true",
    KEY_KB_EXTRACT_PROVIDER: "legacy",
    KEY_KB_PDF_INSPECTOR_ENABLED: "false",
    KEY_KB_SEARCH_MIN_SCORE: str(KB_SEARCH_MIN_SCORE),
    KEY_KB_SEARCH_BOOST_KEYWORD_BONUS: str(KB_SEARCH_BOOST_KEYWORD_BONUS),
    KEY_KB_SEARCH_MMR_LAMBDA: str(KB_SEARCH_MMR_LAMBDA),
    KEY_KB_SEARCH_FILENAME_BOOST: str(KB_SEARCH_FILENAME_BOOST),
    KEY_KB_SEARCH_MODALITY_BOOST: str(KB_SEARCH_MODALITY_BOOST),
    KEY_KB_SEARCH_MODALITY_BOOST_ENABLED: "false",
    KEY_KB_SEARCH_DEFAULT_TOP_K: str(KB_SEARCH_TOP_K_DEFAULT),
    KEY_KB_VOICE_NOTIFY_ENABLED: "true",
    KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS: "120",
    KEY_KB_FTS_CONFIG: "zh_cn",
    KEY_KB_WIKI_LINT_INTERVAL_HOURS: "0",
    KEY_KB_WIKI_COMPILE_MIN_SOURCES: "2",
    KEY_KB_SEARCH_CACHE_ENABLED: "false",
    KEY_KB_SEARCH_CACHE_SIMILARITY_THRESHOLD: "0.85",
    KEY_KB_SEARCH_CACHE_TTL_HOURS: "168",
    KEY_KB_SEARCH_CACHE_MAX_ENTRIES_PER_USER: "500",
    KEY_KB_EVIDENCE_LONG_DOC_CHARS: "8000",
    KEY_KB_EVIDENCE_SAMPLE_K_DEFAULT: "5",
    KEY_KB_EVIDENCE_MONTE_CARLO_MAX_FILES: "3",
    KEY_KB_ENTITY_EXTRACT_ENABLED: "false",
    KEY_KB_SAG_EVENT_EXTRACT_ENABLED: "false",
    KEY_KB_SAG_EVENT_EXTRACT_MODE: "rule",
    KEY_KB_SAG_EVENT_PROMPT_VERSION: "1",
    KEY_KB_SAG_EVENT_EMBED_ENABLED: "false",
    KEY_KB_SAG_QUERY_LLM_ENABLED: "false",
    KEY_KB_RAPTOR_ENABLED: "false",
    KEY_KB_RAPTOR_MIN_CHARS: "30000",
    KEY_KB_RAPTOR_MAX_LEVELS: "3",
    KEY_KB_RAPTOR_MAX_SUMMARIES_PER_FILE: "32",
    KEY_KB_RAPTOR_OLLAMA_TIMEOUT_SEC: "120",
    KEY_KB_RAPTOR_FAIL_OPEN: "true",
    KEY_KB_RAPTOR_DRILL_K: "5",
    KEY_KB_RAPTOR_DRILL_SCORE_FACTOR: "0.95",
    KEY_KB_MULTI_REPR_ENABLED: "false",
    KEY_KB_LARGE_DOC_CHAR_THRESHOLD: "400000",
    KEY_KB_LARGE_DOC_CHUNK_SIZE: "1800",
    KEY_KB_LARGE_DOC_CHUNK_OVERLAP: "150",
    KEY_KB_LARGE_DOC_POST_ENABLED: "false",
    KEY_KB_LARGE_DOC_RAPTOR_ENABLED: "false",
    KEY_KB_RAGAS_ONLINE_EVAL_ENABLED: "false",
    KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE: "1.0",
    KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS: "600",
    KEY_KB_RAGAS_LLM_PROVIDER: "ollama",
    KEY_KB_RAGAS_LLM_BASE_URL: "",
    KEY_KB_RAGAS_LLM_API_KEY: "",
    KEY_KB_RAGAS_LLM_MODEL: "",
    KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS: "90",
    KEY_KB_RAGAS_EVAL_CONCURRENCY: "1",
    KEY_KB_RAGAS_EVAL_CONTEXT_MAX_COUNT: "8",
    KEY_KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM: "1200",
    KEY_KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS: "10000",
    KEY_KB_EXTRACT_INSAVLO_ENABLED: "false",
    KEY_KB_EXTRACT_INSAVLO_BASE_URL: "https://demo.insavlo.com/insavlo/public-api",
    KEY_KB_EXTRACT_INSAVLO_API_KEY: "",
    KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET: "",
    KEY_KB_EXTRACT_INSAVLO_SKILL_CODE: "",
    KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN: "",
    KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS: "24",  # legacy(063): migration read only
    KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES: "120",
    KEY_KB_INGESTION_PIPELINE_JSON: "",
    KEY_OLLAMA_BASE_URL: OLLAMA_BASE_URL.rstrip("/"),
    KEY_OLLAMA_EMBED_MODEL: OLLAMA_EMBED_MODEL,
    KEY_OLLAMA_EMBED_DIM: str(OLLAMA_EMBED_DIM),
    KEY_OLLAMA_CHAT_MODEL: OLLAMA_CHAT_MODEL,
    KEY_OLLAMA_TIMEOUT_SEC: str(OLLAMA_TIMEOUT_SEC),
    KEY_OLLAMA_EMBED_BATCH_SIZE: str(OLLAMA_EMBED_BATCH_SIZE),
    KEY_OLLAMA_NUM_PARALLEL: "4",
    KEY_OLLAMA_EMBED_CONCURRENCY: "4",
    KEY_OLLAMA_API_KEY: "",
    KEY_KB_POST_LLM_PROVIDER: "ollama",
    KEY_KB_POST_LLM_BASE_URL: "",
    KEY_KB_POST_LLM_API_KEY: "",
    KEY_KB_POST_LLM_MODEL: "",
    KEY_KB_POST_LLM_TIMEOUT_SEC: "60",
    KEY_KB_POST_LLM_JSON_MODE: "auto",
    KEY_MINERU_MIN_BATCH_MODE: "auto",
    KEY_MINERU_MIN_BATCH_INFERENCE_SIZE: "112",
    KEY_MINERU_MIN_BATCH_FLOOR: "16",
    KEY_MINERU_PARSE_METHOD: "auto",
    KEY_MINERU_FORMULA_ENABLE: "true",
    KEY_MINERU_TABLE_ENABLE: "true",
    KEY_MINERU_PARSE_TIMEOUT_SEC: "1200",
    KEY_MINERU_RPC_TIMEOUT_SEC: "3600",
    KEY_MINERU_PAGE_CHUNK_ENABLED: "true",
    KEY_MINERU_PAGE_CHUNK_THRESHOLD: "160",
    KEY_MINERU_PAGE_CHUNK_PAGES: "64",
    KEY_MINERU_TABLE_AUTO_ROTATE: "false",
    KEY_MINERU_TABLE_ROTATE_MAX_TABLES: "8",
    KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC: "30",
    KEY_AGENT_SKILL_INSTALL_PROMPT: "请为我安装「钉」智能体技能（FileX 资料库，斜杠 /ding），适用于 OpenClaw、Hermes、OpenHuman、WorkBuddy、Claude Code、Codex、Cursor 等智能体。\n\n站点根 URL：{{ORIGIN}}\n\n请按顺序执行：\n1. 下载技能包（无需鉴权）：\n   curl -fsSL \"{{ORIGIN}}/filex-skill-update\" -o /tmp/filex-skill.zip\n2. 解压到本智能体的 skills 根目录，使得到：\n   skills/ding/SKILL.md\n   skills/ding/modules/\n   skills/ding/references/filex-agent-api.md\n   （覆盖旧文件；skills 目录以你当前运行环境为准，例如 Hermes ~/.hermes/skills、Cursor ~/.cursor/skills 或项目 .cursor/skills）\n3. 若需「链接 URL 入库」，另下载参考实现（.py 模板）：\n   curl -fsSL \"{{ORIGIN}}/filex-skill-agent-update\" -o /tmp/filex-skill-agent.zip\n   unzip -o /tmp/filex-skill-agent.zip -d <skills根目录>\n   得到 skills/ding/agent/filex_ingest_url.py 后执行：\n   pip install -r skills/ding/agent/requirements.txt\n   playwright install chromium\n   （详见 skills/ding/modules/url-ingest.md）\n4. 配置 FileX 鉴权（库内检索/入库必需；外网 research 可暂不配）：\n   - 环境变量：FILEX_ORIGIN={{ORIGIN}}（无尾部斜杠）、FILEX_API_KEY={{API_KEY}}（FileX Web「API 密钥」创建并 reveal；勿用登录 JWT）\n   - Hermes：编辑 ~/.hermes/.env 写入上述两行；改后重启 Gateway\n   - 其它平台（Cursor/Codex/Claude Code/OpenClaw/WorkBuddy 等）：在智能体宿主进程可读的位置配置同名环境变量\n   - 验证：curl -s -H \"Authorization: Bearer $FILEX_API_KEY\" \"$FILEX_ORIGIN/api/external/api-key-status\" 应返回 valid:true 与 username\n   - 已安装 agent 会在每次调用钉入口前自动检查更新，仅当版本/SHA256 不一致时才下载并校验 zip；改 env 后无需重装 zip\n5. 安装完成后创建「钉安装备忘」，以后新对话先读备忘，不重复安装：\n   - 推荐位置：Hermes 写 ~/.hermes/skills/ding/INSTALLATION.md；Codex/Claude Code/Cursor 写项目 .agent/ding-installation.md；其它平台写入长期记忆/skills notes\n   - 记录：FILEX_ORIGIN、skills/ding 路径、skill 版本、skill_zip_sha256、agent_version、agent_zip_sha256、调用方式、依赖状态、验证结果、环境变量配置位置\n   - 安全：备忘不写完整 FILEX_API_KEY，只记录 fb_...末尾4位和配置位置\n6. 升级后检查版本匹配：\n   - 本地：LOCAL_SKILL_VERSION=\"$(tr -d '[:space:]' < <skills根目录>/ding/skill.version)\"\n   - 服务器：SERVER_SKILL_VERSION=\"$(curl -fsS -H \"Authorization: Bearer $FILEX_API_KEY\" \"$FILEX_ORIGIN/api/filex-skill/manifest\" | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"skill_version\"])')\"\n   - 必须满足 test \"$LOCAL_SKILL_VERSION\" = \"$SERVER_SKILL_VERSION\"；不一致时勿宣称安装/升级完成。",
}

TAG_GRAPH_SINGLE_MIN = 8
TAG_GRAPH_SINGLE_MAX = 160

TAG_GRAPH_NODE_DISPLAY_RATIO_MIN = 0.1
TAG_GRAPH_NODE_DISPLAY_RATIO_MAX = 5.0

TAG_GRAPH_EDGE_LINE_WIDTH_MIN = 1
TAG_GRAPH_EDGE_LINE_WIDTH_MAX = 12

MAX_UPLOAD_SIZE_MB_MIN = 1
MAX_UPLOAD_SIZE_MB_MAX = 10240
WORKSPACE_BACKUP_MAX_MB_MIN = 1
WORKSPACE_BACKUP_MAX_MB_MAX = 10240

KB_INDEX_MAX_ATTEMPTS_MIN = 1
AGENT_RUN_RETENTION_DAYS_MIN = 1
AGENT_RUN_RETENTION_DAYS_MAX = 365
KB_INDEX_MAX_ATTEMPTS_MAX = 10
KB_POST_MAX_ATTEMPTS_MIN = 1
KB_POST_MAX_ATTEMPTS_MAX = 10

KB_SEARCH_MIN_SCORE_MIN = 0.0
KB_SEARCH_MIN_SCORE_MAX = 1.0
KB_SEARCH_BOOST_KEYWORD_BONUS_MIN = 0.0
KB_SEARCH_BOOST_KEYWORD_BONUS_MAX = 0.5
KB_SEARCH_MMR_LAMBDA_MIN = 0.0
KB_SEARCH_MMR_LAMBDA_MAX = 1.0
KB_SEARCH_FILENAME_BOOST_MIN = 0.0
KB_SEARCH_FILENAME_BOOST_MAX = 0.5
KB_SEARCH_MODALITY_BOOST_MIN = 0.0
KB_SEARCH_MODALITY_BOOST_MAX = 0.5

KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS_MIN = 1
KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS_MAX = 3600
KB_SEARCH_DEFAULT_TOP_K_MIN = 5
KB_SEARCH_DEFAULT_TOP_K_MAX = KB_SEARCH_TOP_K_MAX
KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MIN = 2
KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MAX = 120
OLLAMA_TIMEOUT_SEC_MIN = 10.0
OLLAMA_TIMEOUT_SEC_MAX = 600.0
OLLAMA_EMBED_BATCH_SIZE_MIN = 1
OLLAMA_EMBED_BATCH_SIZE_MAX = 64
OLLAMA_EMBED_DIM_MIN = 128
OLLAMA_EMBED_DIM_MAX = 4096
KB_POST_LLM_TIMEOUT_SEC_MIN = 5.0
KB_POST_LLM_TIMEOUT_SEC_MAX = 300.0
KB_RAGAS_LLM_TIMEOUT_SECONDS_MIN = 10
KB_RAGAS_LLM_TIMEOUT_SECONDS_MAX = 300
KB_RAGAS_EVAL_CONCURRENCY_MIN = 1
KB_RAGAS_EVAL_CONCURRENCY_MAX = 4
KB_RAGAS_EVAL_CONTEXT_MAX_COUNT_MIN = 1
KB_RAGAS_EVAL_CONTEXT_MAX_COUNT_MAX = 20
KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM_MIN = 200
KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM_MAX = 4000
KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS_MIN = 1000
KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS_MAX = 40000
MINERU_BATCH_MIN = 8
MINERU_BATCH_MAX = 384
MINERU_CHUNK_PAGES_MIN = 8
MINERU_CHUNK_PAGES_MAX = 200
MINERU_PARSE_TIMEOUT_MIN = 60
MINERU_PARSE_TIMEOUT_MAX = 3600
MINERU_RPC_TIMEOUT_MIN = 60
MINERU_RPC_TIMEOUT_MAX = 7200
MINERU_PAGE_CHUNK_THRESHOLD_MIN = 1
MINERU_PAGE_CHUNK_THRESHOLD_MAX = 2000
INSAVLO_TIMEOUT_MIGRATION_LOCK_KEY = 900063

MAX_PREFIX_SUFFIX_LEN = 16_384
SKIP_EMPTY_UPDATE_KEYS = frozenset(
    {
        KEY_KB_EXTRACT_INSAVLO_API_KEY,
        KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET,
        KEY_OLLAMA_API_KEY,
        KEY_KB_POST_LLM_API_KEY,
        KEY_KB_RAGAS_LLM_API_KEY,
    }
)


def insavlo_credential_from_stored(stored: str) -> str:
    """Read Insavlo API Key / Webhook Secret from DB (plaintext or legacy Fernet blob)."""
    raw = str(stored or "").strip()
    if not raw:
        return ""
    from utils.api_key_secret import decrypt_api_key_plaintext

    try:
        return decrypt_api_key_plaintext(raw)
    except ValueError:
        return raw


def secret_credential_from_stored(stored: str) -> str:
    """Read a stored secret that may be plaintext or a legacy encrypted blob."""
    return insavlo_credential_from_stored(stored)


_kb_index_max_attempts_cache: tuple[float, int] | None = None
_kb_index_max_attempts_cache_ttl_sec = 30.0


def _parse_tag_graph_single(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_TAG_GRAPH_SINGLE])
    return max(TAG_GRAPH_SINGLE_MIN, min(TAG_GRAPH_SINGLE_MAX, n))


def _parse_tag_graph_node_display_ratio(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_TAG_GRAPH_NODE_DISPLAY_RATIO])
    clamped = max(TAG_GRAPH_NODE_DISPLAY_RATIO_MIN, min(TAG_GRAPH_NODE_DISPLAY_RATIO_MAX, n))
    return round(clamped, 2)


def _parse_tag_graph_edge_line_width(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_TAG_GRAPH_EDGE_LINE_WIDTH])
    return max(TAG_GRAPH_EDGE_LINE_WIDTH_MIN, min(TAG_GRAPH_EDGE_LINE_WIDTH_MAX, n))


def _parse_kb_index_max_attempts(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_INDEX_MAX_ATTEMPTS])
    return max(KB_INDEX_MAX_ATTEMPTS_MIN, min(KB_INDEX_MAX_ATTEMPTS_MAX, n))


def _parse_kb_post_max_attempts(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_POST_MAX_ATTEMPTS])
    return max(KB_POST_MAX_ATTEMPTS_MIN, min(KB_POST_MAX_ATTEMPTS_MAX, n))


def _parse_agent_run_retention_days(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_AGENT_RUN_RETENTION_DAYS])
    return max(AGENT_RUN_RETENTION_DAYS_MIN, min(AGENT_RUN_RETENTION_DAYS_MAX, n))


def _parse_max_upload_size_mb(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_MAX_UPLOAD_SIZE_MB])
    return max(MAX_UPLOAD_SIZE_MB_MIN, min(MAX_UPLOAD_SIZE_MB_MAX, n))


def _parse_workspace_backup_max_mb(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_WORKSPACE_BACKUP_MAX_MB])
    return max(WORKSPACE_BACKUP_MAX_MB_MIN, min(WORKSPACE_BACKUP_MAX_MB_MAX, n))


def _parse_bool_setting(raw: str) -> bool:
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _parse_enterprise_rbac_write_mode(raw: str) -> str:
    mode = str(raw).strip().lower()
    if mode in ("dual", "new_only"):
        return mode
    return DEFAULTS[KEY_ENTERPRISE_RBAC_WRITE_MODE]


def is_shared_workspaces_enabled(db: Session) -> bool:
    d = get_public_settings_dict(db)
    return _parse_bool_setting(d.get(KEY_SHARED_WORKSPACES_ENABLED, DEFAULTS[KEY_SHARED_WORKSPACES_ENABLED]))


def is_enterprise_rbac_enabled(db: Session) -> bool:
    d = get_public_settings_dict(db)
    return _parse_bool_setting(d.get(KEY_ENTERPRISE_RBAC_ENABLED, DEFAULTS[KEY_ENTERPRISE_RBAC_ENABLED]))




def is_enterprise_rbac_cutover(db: Session) -> bool:
    d = get_public_settings_dict(db)
    return _parse_bool_setting(d.get(KEY_ENTERPRISE_RBAC_CUTOVER, DEFAULTS[KEY_ENTERPRISE_RBAC_CUTOVER]))

def get_enterprise_rbac_write_mode(db: Session) -> str:
    d = get_public_settings_dict(db)
    return _parse_enterprise_rbac_write_mode(
        d.get(KEY_ENTERPRISE_RBAC_WRITE_MODE, DEFAULTS[KEY_ENTERPRISE_RBAC_WRITE_MODE])
    )


def is_kb_search_modality_boost_enabled(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> bool:
    d = _settings_dict(db, user_id=user_id, effective=effective)
    return _parse_bool_setting(d.get(KEY_KB_SEARCH_MODALITY_BOOST_ENABLED, DEFAULTS[KEY_KB_SEARCH_MODALITY_BOOST_ENABLED]))


def is_kb_search_hybrid_enabled(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> bool:
    d = _settings_dict(db, user_id=user_id, effective=effective)
    return _parse_bool_setting(d.get(KEY_KB_SEARCH_HYBRID_ENABLED, DEFAULTS[KEY_KB_SEARCH_HYBRID_ENABLED]))


@dataclass(frozen=True)
class KbSearchTagCoocSettings:
    enabled: bool
    min_edge: int


def _parse_kb_search_tag_cooc_min_edge(raw: str | None) -> int:
    if raw is None or not str(raw).strip():
        return TAG_COOC_MIN_EDGE_DEFAULT
    try:
        n = int(str(raw).strip())
    except ValueError:
        return TAG_COOC_MIN_EDGE_DEFAULT
    return max(1, n)


def get_kb_search_tag_cooc_settings(db: Session) -> KbSearchTagCoocSettings:
    d = get_public_settings_dict(db)
    enabled = _parse_bool_setting(
        d.get(KEY_KB_SEARCH_TAG_COOC_ENABLED, DEFAULTS[KEY_KB_SEARCH_TAG_COOC_ENABLED])
    )
    min_edge = _parse_kb_search_tag_cooc_min_edge(
        d.get(KEY_KB_SEARCH_TAG_COOC_MIN_EDGE, DEFAULTS[KEY_KB_SEARCH_TAG_COOC_MIN_EDGE])
    )
    return KbSearchTagCoocSettings(enabled=enabled, min_edge=min_edge)


def is_kb_search_tag_cooc_enabled(db: Session) -> bool:
    return get_kb_search_tag_cooc_settings(db).enabled


def is_tag_graph_enabled(db: Session) -> bool:
    d = get_public_settings_dict(db)
    return _parse_bool_setting(d.get(KEY_TAG_GRAPH_ENABLED, DEFAULTS[KEY_TAG_GRAPH_ENABLED]))


def is_kb_voice_notify_enabled(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> bool:
    d = _settings_dict(db, user_id=user_id, effective=effective)
    return _parse_bool_setting(
        d.get(KEY_KB_VOICE_NOTIFY_ENABLED, DEFAULTS[KEY_KB_VOICE_NOTIFY_ENABLED])
    )


def is_kb_search_cache_enabled(db: Session) -> bool:
    d = get_public_settings_dict(db)
    return _parse_bool_setting(d.get(KEY_KB_SEARCH_CACHE_ENABLED, DEFAULTS[KEY_KB_SEARCH_CACHE_ENABLED]))


def _parse_kb_search_cache_similarity_threshold(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_KB_SEARCH_CACHE_SIMILARITY_THRESHOLD])
    return round(max(0.5, min(0.99, n)), 3)


def _parse_kb_search_cache_ttl_hours(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_KB_SEARCH_CACHE_TTL_HOURS])
    return max(1.0, min(8760.0, n))


def _parse_kb_search_cache_max_entries(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_SEARCH_CACHE_MAX_ENTRIES_PER_USER])
    return max(10, min(10000, n))


def _parse_kb_evidence_long_doc_chars(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_EVIDENCE_LONG_DOC_CHARS])
    return max(1000, min(500_000, n))


def _parse_kb_evidence_sample_k_default(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_EVIDENCE_SAMPLE_K_DEFAULT])
    return max(1, min(20, n))


def _parse_kb_evidence_monte_carlo_max_files(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_EVIDENCE_MONTE_CARLO_MAX_FILES])
    return max(1, min(10, n))


@dataclass(frozen=True)
class KbSearchCacheSettings:
    enabled: bool
    similarity_threshold: float
    ttl_hours: float
    max_entries_per_user: int


@dataclass(frozen=True)
class KbEvidenceSettings:
    long_doc_chars: int
    sample_k_default: int
    monte_carlo_max_files: int


@dataclass(frozen=True)
class KbRaptorSettings:
    enabled: bool
    min_chars: int
    max_levels: int
    max_summaries_per_file: int
    ollama_timeout_sec: float
    fail_open: bool
    drill_k: int
    drill_score_factor: float


def get_kb_search_cache_settings(db: Session) -> KbSearchCacheSettings:
    d = get_public_settings_dict(db)
    return KbSearchCacheSettings(
        enabled=is_kb_search_cache_enabled(db),
        similarity_threshold=_parse_kb_search_cache_similarity_threshold(
            d.get(KEY_KB_SEARCH_CACHE_SIMILARITY_THRESHOLD, DEFAULTS[KEY_KB_SEARCH_CACHE_SIMILARITY_THRESHOLD])
        ),
        ttl_hours=_parse_kb_search_cache_ttl_hours(
            d.get(KEY_KB_SEARCH_CACHE_TTL_HOURS, DEFAULTS[KEY_KB_SEARCH_CACHE_TTL_HOURS])
        ),
        max_entries_per_user=_parse_kb_search_cache_max_entries(
            d.get(
                KEY_KB_SEARCH_CACHE_MAX_ENTRIES_PER_USER,
                DEFAULTS[KEY_KB_SEARCH_CACHE_MAX_ENTRIES_PER_USER],
            )
        ),
    )


def get_kb_evidence_settings(db: Session) -> KbEvidenceSettings:
    d = get_public_settings_dict(db)
    return KbEvidenceSettings(
        long_doc_chars=_parse_kb_evidence_long_doc_chars(
            d.get(KEY_KB_EVIDENCE_LONG_DOC_CHARS, DEFAULTS[KEY_KB_EVIDENCE_LONG_DOC_CHARS])
        ),
        sample_k_default=_parse_kb_evidence_sample_k_default(
            d.get(KEY_KB_EVIDENCE_SAMPLE_K_DEFAULT, DEFAULTS[KEY_KB_EVIDENCE_SAMPLE_K_DEFAULT])
        ),
        monte_carlo_max_files=_parse_kb_evidence_monte_carlo_max_files(
            d.get(
                KEY_KB_EVIDENCE_MONTE_CARLO_MAX_FILES,
                DEFAULTS[KEY_KB_EVIDENCE_MONTE_CARLO_MAX_FILES],
            )
        ),
    )


def _parse_kb_raptor_min_chars(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_RAPTOR_MIN_CHARS])
    return max(1000, min(500000, n))


def _parse_kb_raptor_max_levels(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_RAPTOR_MAX_LEVELS])
    return max(1, min(8, n))


def _parse_kb_raptor_max_summaries(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_RAPTOR_MAX_SUMMARIES_PER_FILE])
    return max(1, min(128, n))


def _parse_kb_raptor_timeout_sec(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_KB_RAPTOR_OLLAMA_TIMEOUT_SEC])
    return max(10.0, min(600.0, n))


def _parse_kb_raptor_drill_k(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_RAPTOR_DRILL_K])
    return max(1, min(20, n))


def _parse_kb_raptor_drill_score_factor(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_KB_RAPTOR_DRILL_SCORE_FACTOR])
    return round(max(0.5, min(1.0, n)), 2)


def _parse_kb_large_doc_char_threshold(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_LARGE_DOC_CHAR_THRESHOLD])
    return max(10000, min(10_000_000, n))


def _parse_kb_large_doc_chunk_size(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_LARGE_DOC_CHUNK_SIZE])
    return max(200, min(8000, n))


def _parse_kb_large_doc_chunk_overlap(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_LARGE_DOC_CHUNK_OVERLAP])
    return max(0, min(2000, n))


def get_kb_raptor_settings(db: Session) -> KbRaptorSettings:
    d = get_public_settings_dict(db)
    return KbRaptorSettings(
        enabled=_parse_bool_setting(d.get(KEY_KB_RAPTOR_ENABLED, DEFAULTS[KEY_KB_RAPTOR_ENABLED])),
        min_chars=_parse_kb_raptor_min_chars(
            d.get(KEY_KB_RAPTOR_MIN_CHARS, DEFAULTS[KEY_KB_RAPTOR_MIN_CHARS])
        ),
        max_levels=_parse_kb_raptor_max_levels(
            d.get(KEY_KB_RAPTOR_MAX_LEVELS, DEFAULTS[KEY_KB_RAPTOR_MAX_LEVELS])
        ),
        max_summaries_per_file=_parse_kb_raptor_max_summaries(
            d.get(KEY_KB_RAPTOR_MAX_SUMMARIES_PER_FILE, DEFAULTS[KEY_KB_RAPTOR_MAX_SUMMARIES_PER_FILE])
        ),
        ollama_timeout_sec=_parse_kb_raptor_timeout_sec(
            d.get(KEY_KB_RAPTOR_OLLAMA_TIMEOUT_SEC, DEFAULTS[KEY_KB_RAPTOR_OLLAMA_TIMEOUT_SEC])
        ),
        fail_open=_parse_bool_setting(d.get(KEY_KB_RAPTOR_FAIL_OPEN, DEFAULTS[KEY_KB_RAPTOR_FAIL_OPEN])),
        drill_k=_parse_kb_raptor_drill_k(d.get(KEY_KB_RAPTOR_DRILL_K, DEFAULTS[KEY_KB_RAPTOR_DRILL_K])),
        drill_score_factor=_parse_kb_raptor_drill_score_factor(
            d.get(KEY_KB_RAPTOR_DRILL_SCORE_FACTOR, DEFAULTS[KEY_KB_RAPTOR_DRILL_SCORE_FACTOR])
        ),
    )


def is_kb_raptor_enabled(db: Session) -> bool:
    d = get_public_settings_dict(db)
    return _parse_bool_setting(d.get(KEY_KB_RAPTOR_ENABLED, DEFAULTS[KEY_KB_RAPTOR_ENABLED]))


def is_kb_multi_repr_enabled(db: Session) -> bool:
    """154: P2 multi-representation search master switch (146 FR-P2-003).

    Default false — 146 P-146-01 向后兼容。管理员在 /admin/settings 显式开启
    后，router 才会向 search_kb 透传 multi_repr_enabled=True。
    """
    d = get_public_settings_dict(db)
    return _parse_bool_setting(
        d.get(KEY_KB_MULTI_REPR_ENABLED, DEFAULTS[KEY_KB_MULTI_REPR_ENABLED])
    )


def get_kb_large_doc_settings(db: Session):
    """T-4/101 large doc thresholds and post-processing toggles."""
    d = get_public_settings_dict(db)
    return {
        "char_threshold": _parse_kb_large_doc_char_threshold(
            d.get(KEY_KB_LARGE_DOC_CHAR_THRESHOLD, DEFAULTS[KEY_KB_LARGE_DOC_CHAR_THRESHOLD])
        ),
        "chunk_size": _parse_kb_large_doc_chunk_size(
            d.get(KEY_KB_LARGE_DOC_CHUNK_SIZE, DEFAULTS[KEY_KB_LARGE_DOC_CHUNK_SIZE])
        ),
        "chunk_overlap": _parse_kb_large_doc_chunk_overlap(
            d.get(KEY_KB_LARGE_DOC_CHUNK_OVERLAP, DEFAULTS[KEY_KB_LARGE_DOC_CHUNK_OVERLAP])
        ),
        "post_enabled": _parse_bool_setting(
            d.get(KEY_KB_LARGE_DOC_POST_ENABLED, DEFAULTS[KEY_KB_LARGE_DOC_POST_ENABLED])
        ),
        "raptor_enabled": _parse_bool_setting(
            d.get(KEY_KB_LARGE_DOC_RAPTOR_ENABLED, DEFAULTS[KEY_KB_LARGE_DOC_RAPTOR_ENABLED])
        ),
    }


def is_kb_large_doc_post_enabled(db: Session) -> bool:
    return bool(get_kb_large_doc_settings(db)["post_enabled"])


def is_kb_large_doc_raptor_enabled(db: Session) -> bool:
    return bool(get_kb_large_doc_settings(db)["raptor_enabled"])


KB_CHUNK_PROFILES = frozenset({"default", "long_doc", "qa_pairs", "table_heavy"})

KB_CHUNK_SIZE_MIN = 1
KB_CHUNK_SIZE_MAX = 100000
KB_CHUNK_OVERLAP_MIN = 0


def _format_optional_int_setting(raw: str) -> str:
    parsed = _parse_optional_positive_int(raw)
    return "" if parsed is None else str(parsed)


def _parse_optional_positive_int(raw: str) -> int | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        n = int(s)
    except ValueError:
        return None
    return n if n > 0 else None


def _normalize_kb_chunk_size(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        n = int(s)
    except ValueError as e:
        raise ValueError("kb_chunk_size 须为正整数或留空") from e
    if n <= 0:
        raise ValueError("kb_chunk_size 须大于 0")
    if n > KB_CHUNK_SIZE_MAX:
        raise ValueError(f"kb_chunk_size 不得超过 {KB_CHUNK_SIZE_MAX}")
    return str(n)


def _normalize_kb_chunk_overlap(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        n = int(s)
    except ValueError as e:
        raise ValueError("kb_chunk_overlap 须为非负整数或留空") from e
    if n < KB_CHUNK_OVERLAP_MIN:
        raise ValueError("kb_chunk_overlap 须 >= 0")
    return str(n)


def _parse_kb_embed_cache_enabled(raw: str) -> bool:
    from config import KB_EMBED_CACHE_ENABLED

    s = str(raw or "").strip()
    if not s:
        return KB_EMBED_CACHE_ENABLED
    return _parse_bool_setting(s)


def _kb_embed_effective_max_chars() -> int:
    from services.kb_embed_limits import effective_max_chars_for_current_model

    return effective_max_chars_for_current_model()


def get_kb_chunk_size(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> int | None:
    d = _settings_dict(db, user_id=user_id, effective=effective)
    return _parse_optional_positive_int(d.get(KEY_KB_CHUNK_SIZE, DEFAULTS[KEY_KB_CHUNK_SIZE]))


def get_kb_chunk_overlap(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> int | None:
    d = _settings_dict(db, user_id=user_id, effective=effective)
    return _parse_optional_positive_int(d.get(KEY_KB_CHUNK_OVERLAP, DEFAULTS[KEY_KB_CHUNK_OVERLAP]))


def get_kb_chunk_split_recursive(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> bool:
    d = _settings_dict(db, user_id=user_id, effective=effective)
    return _parse_bool_setting(d.get(KEY_KB_CHUNK_SPLIT_RECURSIVE, DEFAULTS[KEY_KB_CHUNK_SPLIT_RECURSIVE]))


def get_kb_embed_cache_enabled(db: Session) -> bool:
    d = get_public_settings_dict(db)
    return _parse_kb_embed_cache_enabled(d.get(KEY_KB_EMBED_CACHE_ENABLED, DEFAULTS[KEY_KB_EMBED_CACHE_ENABLED]))

KB_EXTRACT_PROVIDERS = frozenset({"legacy", "docling", "mineru", "liteparse", "insavlo"})
KB_REEXTRACT_PROVIDERS = KB_EXTRACT_PROVIDERS


def _parse_kb_chunk_profile(raw: str) -> str:
    name = str(raw).strip().lower()
    return name if name in KB_CHUNK_PROFILES else "default"


def _parse_kb_extract_provider(raw: str) -> str:
    name = str(raw).strip().lower()
    return name if name in KB_EXTRACT_PROVIDERS else "legacy"




def _parse_kb_voice_notify_playback_ttl_seconds(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS])
    return max(
        KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS_MIN,
        min(KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS_MAX, n),
    )


def _parse_kb_search_default_top_k(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_SEARCH_DEFAULT_TOP_K])
    return max(KB_SEARCH_DEFAULT_TOP_K_MIN, min(KB_SEARCH_DEFAULT_TOP_K_MAX, n))


def _parse_kb_extract_insavlo_timeout_minutes(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES])
    return max(
        KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MIN,
        min(KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MAX, n),
    )


def _parse_ollama_embed_dim(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_OLLAMA_EMBED_DIM])
    return max(OLLAMA_EMBED_DIM_MIN, min(OLLAMA_EMBED_DIM_MAX, n))


def _parse_ollama_timeout_sec(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_OLLAMA_TIMEOUT_SEC])
    return max(OLLAMA_TIMEOUT_SEC_MIN, min(OLLAMA_TIMEOUT_SEC_MAX, n))


def _parse_ollama_embed_batch_size(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_OLLAMA_EMBED_BATCH_SIZE])
    return max(OLLAMA_EMBED_BATCH_SIZE_MIN, min(OLLAMA_EMBED_BATCH_SIZE_MAX, n))


OLLAMA_NUM_PARALLEL_MIN = 1
OLLAMA_NUM_PARALLEL_MAX = 32
OLLAMA_EMBED_CONCURRENCY_MIN = 1
OLLAMA_EMBED_CONCURRENCY_MAX = 32


def _parse_ollama_num_parallel(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_OLLAMA_NUM_PARALLEL])
    return max(OLLAMA_NUM_PARALLEL_MIN, min(OLLAMA_NUM_PARALLEL_MAX, n))


def _parse_ollama_embed_concurrency(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_OLLAMA_EMBED_CONCURRENCY])
    return max(OLLAMA_EMBED_CONCURRENCY_MIN, min(OLLAMA_EMBED_CONCURRENCY_MAX, n))


def _parse_kb_post_llm_provider(raw: str) -> str:
    value = str(raw or "").strip().lower() or DEFAULTS[KEY_KB_POST_LLM_PROVIDER]
    if value not in {"ollama", "openai_compatible"}:
        raise ValueError("kb_post_llm_provider 须为 ollama 或 openai_compatible")
    return value


def _parse_kb_post_llm_json_mode(raw: str) -> str:
    value = str(raw or "").strip().lower() or DEFAULTS[KEY_KB_POST_LLM_JSON_MODE]
    if value not in {"auto", "response_format", "prompt_only"}:
        raise ValueError("kb_post_llm_json_mode 须为 auto、response_format 或 prompt_only")
    return value


def _parse_kb_post_llm_timeout_sec(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_KB_POST_LLM_TIMEOUT_SEC])
    return max(KB_POST_LLM_TIMEOUT_SEC_MIN, min(KB_POST_LLM_TIMEOUT_SEC_MAX, n))


def _parse_kb_ragas_llm_provider(raw: str) -> str:
    value = str(raw or "").strip().lower() or DEFAULTS[KEY_KB_RAGAS_LLM_PROVIDER]
    if value not in {"ollama", "openai_compatible"}:
        raise ValueError("kb_ragas_llm_provider 须为 ollama 或 openai_compatible")
    return value


def _parse_ragas_bounded_int(raw: str, *, key: str, minimum: int, maximum: int) -> int:
    try:
        value = int(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"{key} 须为整数") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} 须在 {minimum}–{maximum} 之间")
    return value


def _validate_openai_compatible_base_url(raw: str) -> str:
    from urllib.parse import urlparse

    normalized = str(raw or "").strip().rstrip("/")
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("kb_post_llm_base_url 必须为 http/https 且包含 host")
    return normalized


def _validate_ragas_llm_base_url(raw: str) -> str:
    from urllib.parse import urlparse

    normalized = str(raw or "").strip().rstrip("/")
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("kb_ragas_llm_base_url 必须为 http/https 且包含 host")
    return normalized


def _parse_mineru_batch_mode(raw: str) -> str:
    mode = str(raw).strip().lower()
    if mode in ("fixed", "auto"):
        return mode
    return DEFAULTS[KEY_MINERU_MIN_BATCH_MODE]


def _parse_mineru_batch_size(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_MINERU_MIN_BATCH_INFERENCE_SIZE])
    return max(MINERU_BATCH_MIN, min(MINERU_BATCH_MAX, n))


def _parse_mineru_batch_floor(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_MINERU_MIN_BATCH_FLOOR])
    return max(MINERU_BATCH_MIN, min(MINERU_BATCH_MAX, n))


def _parse_mineru_parse_method(raw: str) -> str:
    method = str(raw).strip().lower()
    if method in ("auto", "txt", "ocr"):
        return method
    return DEFAULTS[KEY_MINERU_PARSE_METHOD]


def _parse_mineru_parse_timeout_sec(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_MINERU_PARSE_TIMEOUT_SEC])
    return max(MINERU_PARSE_TIMEOUT_MIN, min(MINERU_PARSE_TIMEOUT_MAX, n))


def _parse_mineru_rpc_timeout_sec(raw: str) -> int:
    try:
        n = int(float(str(raw).strip()))
    except ValueError:
        return int(DEFAULTS[KEY_MINERU_RPC_TIMEOUT_SEC])
    return max(MINERU_RPC_TIMEOUT_MIN, min(MINERU_RPC_TIMEOUT_MAX, n))


def _parse_mineru_page_chunk_threshold(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_MINERU_PAGE_CHUNK_THRESHOLD])
    return max(MINERU_PAGE_CHUNK_THRESHOLD_MIN, min(MINERU_PAGE_CHUNK_THRESHOLD_MAX, n))


def _parse_mineru_page_chunk_pages(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_MINERU_PAGE_CHUNK_PAGES])
    return max(MINERU_CHUNK_PAGES_MIN, min(MINERU_CHUNK_PAGES_MAX, n))


def _parse_mineru_table_rotate_max_tables(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_MINERU_TABLE_ROTATE_MAX_TABLES])
    return max(1, min(64, n))


def _parse_mineru_table_rotate_timeout_sec(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return int(DEFAULTS[KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC])
    return max(1, min(300, n))


def get_kb_search_default_top_k(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> int:
    if user_id is not None or effective is not None:
        d = _settings_dict(db, user_id=user_id, effective=effective)
        return _parse_kb_search_default_top_k(
            d.get(KEY_KB_SEARCH_DEFAULT_TOP_K, DEFAULTS[KEY_KB_SEARCH_DEFAULT_TOP_K])
        )
    d = get_public_settings_dict(db)
    return _parse_kb_search_default_top_k(
        d.get(KEY_KB_SEARCH_DEFAULT_TOP_K, DEFAULTS[KEY_KB_SEARCH_DEFAULT_TOP_K])
    )

def _parse_kb_search_min_score(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_KB_SEARCH_MIN_SCORE])
    return round(max(KB_SEARCH_MIN_SCORE_MIN, min(KB_SEARCH_MIN_SCORE_MAX, n)), 2)


def _parse_kb_search_boost_keyword_bonus(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_KB_SEARCH_BOOST_KEYWORD_BONUS])
    return round(max(KB_SEARCH_BOOST_KEYWORD_BONUS_MIN, min(KB_SEARCH_BOOST_KEYWORD_BONUS_MAX, n)), 2)




def _parse_kb_fts_config(raw: str) -> str:
    cfg = str(raw).strip().lower()
    if cfg in ("zh_cn", "simple"):
        return cfg
    return DEFAULTS[KEY_KB_FTS_CONFIG]


def _parse_kb_search_modality_boost(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_KB_SEARCH_MODALITY_BOOST])
    return round(max(KB_SEARCH_MODALITY_BOOST_MIN, min(KB_SEARCH_MODALITY_BOOST_MAX, n)), 2)


def _parse_kb_search_filename_boost(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_KB_SEARCH_FILENAME_BOOST])
    return round(max(KB_SEARCH_FILENAME_BOOST_MIN, min(KB_SEARCH_FILENAME_BOOST_MAX, n)), 2)

def _parse_kb_search_mmr_lambda(raw: str) -> float:
    try:
        n = float(str(raw).strip())
    except ValueError:
        return float(DEFAULTS[KEY_KB_SEARCH_MMR_LAMBDA])
    return round(max(KB_SEARCH_MMR_LAMBDA_MIN, min(KB_SEARCH_MMR_LAMBDA_MAX, n)), 2)


@dataclass(frozen=True)
class KbSearchRankSettings:
    """资料库检索rank设置 业务服务。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-29

        Attributes:
            min_score: 最小score（float）。
            boost_keyword_bonus: 加权keywordbonus（float）。
            mmr_lambda: mmrlambda（float）。
            filename_boost: 文件名加权（float）。
            modality_boost: 模态加权（float）。
    """
    min_score: float
    boost_keyword_bonus: float
    mmr_lambda: float
    filename_boost: float
    modality_boost: float


def get_kb_search_rank_settings(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> KbSearchRankSettings:
    d = _settings_dict(db, user_id=user_id, effective=effective)
    return KbSearchRankSettings(
        min_score=_parse_kb_search_min_score(d.get(KEY_KB_SEARCH_MIN_SCORE, DEFAULTS[KEY_KB_SEARCH_MIN_SCORE])),
        boost_keyword_bonus=_parse_kb_search_boost_keyword_bonus(
            d.get(KEY_KB_SEARCH_BOOST_KEYWORD_BONUS, DEFAULTS[KEY_KB_SEARCH_BOOST_KEYWORD_BONUS])
        ),
        mmr_lambda=_parse_kb_search_mmr_lambda(
            d.get(KEY_KB_SEARCH_MMR_LAMBDA, DEFAULTS[KEY_KB_SEARCH_MMR_LAMBDA])
        ),
        filename_boost=_parse_kb_search_filename_boost(
            d.get(KEY_KB_SEARCH_FILENAME_BOOST, DEFAULTS[KEY_KB_SEARCH_FILENAME_BOOST])
        ),
        modality_boost=_parse_kb_search_modality_boost(
            d.get(KEY_KB_SEARCH_MODALITY_BOOST, DEFAULTS[KEY_KB_SEARCH_MODALITY_BOOST])
        )
        if is_kb_search_modality_boost_enabled(db, user_id=user_id, effective=effective)
        else 0.0,
    )


def get_kb_chunk_profile(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> str:
    d = _settings_dict(db, user_id=user_id, effective=effective)
    return _parse_kb_chunk_profile(d.get(KEY_KB_CHUNK_PROFILE, DEFAULTS[KEY_KB_CHUNK_PROFILE]))


def get_kb_ingestion_pipeline_json(db: Session) -> str:
    d = get_public_settings_dict(db)
    return str(d.get(KEY_KB_INGESTION_PIPELINE_JSON, DEFAULTS[KEY_KB_INGESTION_PIPELINE_JSON])).strip()


def get_kb_extract_provider(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> str:
    d = _settings_dict(db, user_id=user_id, effective=effective)
    return _parse_kb_extract_provider(d.get(KEY_KB_EXTRACT_PROVIDER, DEFAULTS[KEY_KB_EXTRACT_PROVIDER]))


def get_kb_pdf_inspector_enabled(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> bool:
    """pdf-inspector 运行时开关（系统参数表，默认关闭）。"""
    d = _settings_dict(db, user_id=user_id, effective=effective)
    return _parse_bool_setting(
        d.get(KEY_KB_PDF_INSPECTOR_ENABLED, DEFAULTS[KEY_KB_PDF_INSPECTOR_ENABLED])
    )


def _get_or_create_row(db: Session, key: str) -> SystemSetting:
    row = db.query(SystemSetting).filter(SystemSetting.setting_key == key).first()
    if row:
        return row
    row = SystemSetting(setting_key=key, value=DEFAULTS.get(key, ""))
    db.add(row)
    db.flush()
    return row


def ensure_mineru_settings_defaults(db: Session) -> bool:
    """Insert missing mineru_* rows from DEFAULTS so UI and kb-extract use persisted values."""
    from models.system_setting import SystemSetting

    existing = {
        key
        for (key,) in db.query(SystemSetting.setting_key)
        .filter(SystemSetting.setting_key.in_(MINERU_SETTING_KEYS))
        .all()
    }
    created = False
    for key in MINERU_SETTING_KEYS:
        if key not in existing:
            db.add(SystemSetting(setting_key=key, value=DEFAULTS[key]))
            created = True
    if created:
        db.commit()
        invalidate_settings_cache()
    return created


def _resolve_insavlo_timeout_minutes_raw(m: dict[str, str]) -> str:
    """063: read minutes key; fallback legacy hours with clamp if migration not yet run."""
    if KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES in m:
        return m[KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES]
    if KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS in m:
        try:
            hours = int(str(m[KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS]).strip())
        except ValueError:
            hours = int(DEFAULTS[KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS])
        return str(
            max(
                KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MIN,
                min(KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MAX, hours * 60),
            )
        )
    return DEFAULTS[KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES]

def _load_from_db(db: Session) -> dict[str, str]:
    load_keys = set(KNOWN_KEYS) | {KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS}
    rows = db.query(SystemSetting).filter(SystemSetting.setting_key.in_(load_keys)).all()
    m = {r.setting_key: r.value for r in rows}
    tag_raw = m.get(KEY_TAG_GRAPH_SINGLE, DEFAULTS[KEY_TAG_GRAPH_SINGLE])
    ratio_raw = m.get(KEY_TAG_GRAPH_NODE_DISPLAY_RATIO, DEFAULTS[KEY_TAG_GRAPH_NODE_DISPLAY_RATIO])
    edge_w_raw = m.get(KEY_TAG_GRAPH_EDGE_LINE_WIDTH, DEFAULTS[KEY_TAG_GRAPH_EDGE_LINE_WIDTH])
    tag_graph_enabled_raw = m.get(KEY_TAG_GRAPH_ENABLED, DEFAULTS[KEY_TAG_GRAPH_ENABLED])
    max_mb_raw = m.get(KEY_MAX_UPLOAD_SIZE_MB, DEFAULTS[KEY_MAX_UPLOAD_SIZE_MB])
    workspace_backup_max_mb_raw = m.get(
        KEY_WORKSPACE_BACKUP_MAX_MB, DEFAULTS[KEY_WORKSPACE_BACKUP_MAX_MB]
    )
    attempts_raw = m.get(KEY_KB_INDEX_MAX_ATTEMPTS, DEFAULTS[KEY_KB_INDEX_MAX_ATTEMPTS])
    shared_raw = m.get(KEY_SHARED_WORKSPACES_ENABLED, DEFAULTS[KEY_SHARED_WORKSPACES_ENABLED])
    rbac_enabled_raw = m.get(KEY_ENTERPRISE_RBAC_ENABLED, DEFAULTS[KEY_ENTERPRISE_RBAC_ENABLED])
    rbac_write_mode_raw = m.get(KEY_ENTERPRISE_RBAC_WRITE_MODE, DEFAULTS[KEY_ENTERPRISE_RBAC_WRITE_MODE])
    hybrid_raw = m.get(KEY_KB_SEARCH_HYBRID_ENABLED, DEFAULTS[KEY_KB_SEARCH_HYBRID_ENABLED])
    tag_cooc_enabled_raw = m.get(KEY_KB_SEARCH_TAG_COOC_ENABLED, DEFAULTS[KEY_KB_SEARCH_TAG_COOC_ENABLED])
    tag_cooc_min_edge_raw = m.get(KEY_KB_SEARCH_TAG_COOC_MIN_EDGE, DEFAULTS[KEY_KB_SEARCH_TAG_COOC_MIN_EDGE])
    min_score_raw = m.get(KEY_KB_SEARCH_MIN_SCORE, DEFAULTS[KEY_KB_SEARCH_MIN_SCORE])
    boost_raw = m.get(KEY_KB_SEARCH_BOOST_KEYWORD_BONUS, DEFAULTS[KEY_KB_SEARCH_BOOST_KEYWORD_BONUS])
    mmr_raw = m.get(KEY_KB_SEARCH_MMR_LAMBDA, DEFAULTS[KEY_KB_SEARCH_MMR_LAMBDA])
    filename_boost_raw = m.get(KEY_KB_SEARCH_FILENAME_BOOST, DEFAULTS[KEY_KB_SEARCH_FILENAME_BOOST])
    modality_boost_raw = m.get(KEY_KB_SEARCH_MODALITY_BOOST, DEFAULTS[KEY_KB_SEARCH_MODALITY_BOOST])
    modality_boost_enabled_raw = m.get(KEY_KB_SEARCH_MODALITY_BOOST_ENABLED, DEFAULTS[KEY_KB_SEARCH_MODALITY_BOOST_ENABLED])
    default_top_k_raw = m.get(KEY_KB_SEARCH_DEFAULT_TOP_K, DEFAULTS[KEY_KB_SEARCH_DEFAULT_TOP_K])
    voice_notify_raw = m.get(KEY_KB_VOICE_NOTIFY_ENABLED, DEFAULTS[KEY_KB_VOICE_NOTIFY_ENABLED])
    voice_playback_ttl_raw = m.get(
        KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS, DEFAULTS[KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS]
    )
    insavlo_enabled_raw = m.get(KEY_KB_EXTRACT_INSAVLO_ENABLED, DEFAULTS[KEY_KB_EXTRACT_INSAVLO_ENABLED])
    insavlo_timeout_raw = _resolve_insavlo_timeout_minutes_raw(m)
    insavlo_api_key_plain = insavlo_credential_from_stored(m.get(KEY_KB_EXTRACT_INSAVLO_API_KEY, ""))
    insavlo_has_api_key = bool(insavlo_api_key_plain)
    insavlo_webhook_secret_plain = insavlo_credential_from_stored(
        m.get(KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET, "")
    )
    insavlo_has_webhook_secret = bool(insavlo_webhook_secret_plain)
    kb_post_llm_api_key_plain = secret_credential_from_stored(m.get(KEY_KB_POST_LLM_API_KEY, ""))
    kb_post_llm_has_api_key = bool(kb_post_llm_api_key_plain)
    ollama_api_key_plain = secret_credential_from_stored(m.get(KEY_OLLAMA_API_KEY, ""))
    ollama_has_api_key = bool(ollama_api_key_plain)
    kb_ragas_llm_api_key_plain = secret_credential_from_stored(m.get(KEY_KB_RAGAS_LLM_API_KEY, ""))
    kb_ragas_llm_has_api_key = bool(kb_ragas_llm_api_key_plain)
    loaded = {
        "clipboard_prefix": m.get(KEY_CLIPBOARD_PREFIX, DEFAULTS[KEY_CLIPBOARD_PREFIX]),
        "clipboard_suffix": m.get(KEY_CLIPBOARD_SUFFIX, DEFAULTS[KEY_CLIPBOARD_SUFFIX]),
        "tag_graph_single_node_symbol_size": str(_parse_tag_graph_single(tag_raw)),
        "tag_graph_node_display_ratio": str(_parse_tag_graph_node_display_ratio(ratio_raw)),
        "tag_graph_edge_line_width": str(_parse_tag_graph_edge_line_width(edge_w_raw)),
        "tag_graph_enabled": "true" if _parse_bool_setting(tag_graph_enabled_raw) else "false",
        "max_upload_size_mb": str(_parse_max_upload_size_mb(max_mb_raw)),
        "workspace_backup_max_mb": str(_parse_workspace_backup_max_mb(workspace_backup_max_mb_raw)),
        "kb_index_max_attempts": str(_parse_kb_index_max_attempts(attempts_raw)),
        "kb_post_async_enabled": "true"
        if _parse_bool_setting(m.get(KEY_KB_POST_ASYNC_ENABLED, DEFAULTS[KEY_KB_POST_ASYNC_ENABLED]))
        else "false",
        "kb_post_max_attempts": str(
            _parse_kb_post_max_attempts(m.get(KEY_KB_POST_MAX_ATTEMPTS, DEFAULTS[KEY_KB_POST_MAX_ATTEMPTS]))
        ),
        "agent_run_retention_days": str(
            _parse_agent_run_retention_days(
                m.get(KEY_AGENT_RUN_RETENTION_DAYS, DEFAULTS[KEY_AGENT_RUN_RETENTION_DAYS])
            )
        ),
        "shared_workspaces_enabled": "true" if _parse_bool_setting(shared_raw) else "false",
        "enterprise_rbac_enabled": "true" if _parse_bool_setting(rbac_enabled_raw) else "false",
        "enterprise_rbac_write_mode": _parse_enterprise_rbac_write_mode(rbac_write_mode_raw),
        "enterprise_rbac_cutover": "true" if _parse_bool_setting(m.get(KEY_ENTERPRISE_RBAC_CUTOVER, DEFAULTS[KEY_ENTERPRISE_RBAC_CUTOVER])) else "false",
        "kb_search_hybrid_enabled": "true" if _parse_bool_setting(hybrid_raw) else "false",
        KEY_KB_SEARCH_TAG_COOC_ENABLED: "true" if _parse_bool_setting(tag_cooc_enabled_raw) else "false",
        KEY_KB_SEARCH_TAG_COOC_MIN_EDGE: str(_parse_kb_search_tag_cooc_min_edge(tag_cooc_min_edge_raw)),
        "kb_chunk_profile": _parse_kb_chunk_profile(m.get(KEY_KB_CHUNK_PROFILE, DEFAULTS[KEY_KB_CHUNK_PROFILE])),
        "kb_chunk_size": _format_optional_int_setting(m.get(KEY_KB_CHUNK_SIZE, DEFAULTS[KEY_KB_CHUNK_SIZE])),
        "kb_chunk_overlap": _format_optional_int_setting(m.get(KEY_KB_CHUNK_OVERLAP, DEFAULTS[KEY_KB_CHUNK_OVERLAP])),
        "kb_chunk_split_recursive": "true"
        if _parse_bool_setting(m.get(KEY_KB_CHUNK_SPLIT_RECURSIVE, DEFAULTS[KEY_KB_CHUNK_SPLIT_RECURSIVE]))
        else "false",
        "kb_embed_cache_enabled": "true"
        if _parse_kb_embed_cache_enabled(m.get(KEY_KB_EMBED_CACHE_ENABLED, DEFAULTS[KEY_KB_EMBED_CACHE_ENABLED]))
        else "false",
        "kb_embed_effective_max_chars": str(_kb_embed_effective_max_chars()),
        "kb_extract_provider": _parse_kb_extract_provider(m.get(KEY_KB_EXTRACT_PROVIDER, DEFAULTS[KEY_KB_EXTRACT_PROVIDER])),
        "kb_pdf_inspector_enabled": "true"
        if _parse_bool_setting(m.get(KEY_KB_PDF_INSPECTOR_ENABLED, DEFAULTS[KEY_KB_PDF_INSPECTOR_ENABLED]))
        else "false",
        "kb_search_min_score": str(_parse_kb_search_min_score(min_score_raw)),
        "kb_search_boost_keyword_bonus": str(_parse_kb_search_boost_keyword_bonus(boost_raw)),
        "kb_search_mmr_lambda": str(_parse_kb_search_mmr_lambda(mmr_raw)),
        "kb_search_filename_boost": str(_parse_kb_search_filename_boost(filename_boost_raw)),
        "kb_search_modality_boost": str(_parse_kb_search_modality_boost(modality_boost_raw)),
        "kb_search_modality_boost_enabled": str(_parse_bool_setting(modality_boost_enabled_raw)).lower(),
        "kb_search_default_top_k": str(_parse_kb_search_default_top_k(default_top_k_raw)),
        "kb_voice_notify_enabled": "true" if _parse_bool_setting(voice_notify_raw) else "false",
        "kb_voice_notify_playback_ttl_seconds": str(
            _parse_kb_voice_notify_playback_ttl_seconds(voice_playback_ttl_raw)
        ),
        "kb_fts_config": _parse_kb_fts_config(m.get(KEY_KB_FTS_CONFIG, DEFAULTS[KEY_KB_FTS_CONFIG])),
        "kb_wiki_lint_interval_hours": str(_parse_kb_wiki_lint_interval_hours(m.get(KEY_KB_WIKI_LINT_INTERVAL_HOURS, DEFAULTS[KEY_KB_WIKI_LINT_INTERVAL_HOURS]))),
        "kb_wiki_compile_min_sources": str(_parse_kb_wiki_compile_min_sources(m.get(KEY_KB_WIKI_COMPILE_MIN_SOURCES, DEFAULTS[KEY_KB_WIKI_COMPILE_MIN_SOURCES]))),
        "kb_entity_extract_enabled": "true" if _parse_bool_setting(m.get(KEY_KB_ENTITY_EXTRACT_ENABLED, DEFAULTS[KEY_KB_ENTITY_EXTRACT_ENABLED])) else "false",
        "kb_sag_event_extract_enabled": "true"
        if _parse_bool_setting(
            m.get(KEY_KB_SAG_EVENT_EXTRACT_ENABLED, DEFAULTS[KEY_KB_SAG_EVENT_EXTRACT_ENABLED])
        )
        else "false",
        "kb_sag_event_extract_mode": _parse_kb_sag_event_extract_mode(
            m.get(KEY_KB_SAG_EVENT_EXTRACT_MODE, DEFAULTS[KEY_KB_SAG_EVENT_EXTRACT_MODE])
        ),
        "kb_sag_event_prompt_version": str(
            _parse_kb_sag_event_prompt_version(
                m.get(
                    KEY_KB_SAG_EVENT_PROMPT_VERSION,
                    DEFAULTS[KEY_KB_SAG_EVENT_PROMPT_VERSION],
                )
            )
        ),
        "kb_sag_event_embed_enabled": "true"
        if _parse_bool_setting(
            m.get(KEY_KB_SAG_EVENT_EMBED_ENABLED, DEFAULTS[KEY_KB_SAG_EVENT_EMBED_ENABLED])
        )
        else "false",
        "kb_sag_query_llm_enabled": "true"
        if _parse_bool_setting(
            m.get(KEY_KB_SAG_QUERY_LLM_ENABLED, DEFAULTS[KEY_KB_SAG_QUERY_LLM_ENABLED])
        )
        else "false",
        "kb_raptor_enabled": "true"
        if _parse_bool_setting(m.get(KEY_KB_RAPTOR_ENABLED, DEFAULTS[KEY_KB_RAPTOR_ENABLED]))
        else "false",
        "kb_raptor_min_chars": str(
            _parse_kb_raptor_min_chars(m.get(KEY_KB_RAPTOR_MIN_CHARS, DEFAULTS[KEY_KB_RAPTOR_MIN_CHARS]))
        ),
        "kb_raptor_max_levels": str(
            _parse_kb_raptor_max_levels(m.get(KEY_KB_RAPTOR_MAX_LEVELS, DEFAULTS[KEY_KB_RAPTOR_MAX_LEVELS]))
        ),
        "kb_raptor_max_summaries_per_file": str(
            _parse_kb_raptor_max_summaries(
                m.get(KEY_KB_RAPTOR_MAX_SUMMARIES_PER_FILE, DEFAULTS[KEY_KB_RAPTOR_MAX_SUMMARIES_PER_FILE])
            )
        ),
        "kb_raptor_ollama_timeout_sec": str(
            _parse_kb_raptor_timeout_sec(
                m.get(KEY_KB_RAPTOR_OLLAMA_TIMEOUT_SEC, DEFAULTS[KEY_KB_RAPTOR_OLLAMA_TIMEOUT_SEC])
            )
        ),
        "kb_raptor_fail_open": "true"
        if _parse_bool_setting(m.get(KEY_KB_RAPTOR_FAIL_OPEN, DEFAULTS[KEY_KB_RAPTOR_FAIL_OPEN]))
        else "false",
        "kb_raptor_drill_k": str(
            _parse_kb_raptor_drill_k(m.get(KEY_KB_RAPTOR_DRILL_K, DEFAULTS[KEY_KB_RAPTOR_DRILL_K]))
        ),
        "kb_raptor_drill_score_factor": str(
            _parse_kb_raptor_drill_score_factor(
                m.get(KEY_KB_RAPTOR_DRILL_SCORE_FACTOR, DEFAULTS[KEY_KB_RAPTOR_DRILL_SCORE_FACTOR])
            )
        ),
        "kb_multi_repr_enabled": "true"
        if _parse_bool_setting(
            m.get(KEY_KB_MULTI_REPR_ENABLED, DEFAULTS[KEY_KB_MULTI_REPR_ENABLED])
        )
        else "false",
        KEY_KB_LARGE_DOC_CHAR_THRESHOLD: str(
            _parse_kb_large_doc_char_threshold(
                m.get(KEY_KB_LARGE_DOC_CHAR_THRESHOLD, DEFAULTS[KEY_KB_LARGE_DOC_CHAR_THRESHOLD])
            )
        ),
        KEY_KB_LARGE_DOC_CHUNK_SIZE: str(
            _parse_kb_large_doc_chunk_size(
                m.get(KEY_KB_LARGE_DOC_CHUNK_SIZE, DEFAULTS[KEY_KB_LARGE_DOC_CHUNK_SIZE])
            )
        ),
        KEY_KB_LARGE_DOC_CHUNK_OVERLAP: str(
            _parse_kb_large_doc_chunk_overlap(
                m.get(KEY_KB_LARGE_DOC_CHUNK_OVERLAP, DEFAULTS[KEY_KB_LARGE_DOC_CHUNK_OVERLAP])
            )
        ),
        KEY_KB_LARGE_DOC_POST_ENABLED: "true"
        if _parse_bool_setting(
            m.get(KEY_KB_LARGE_DOC_POST_ENABLED, DEFAULTS[KEY_KB_LARGE_DOC_POST_ENABLED])
        )
        else "false",
        KEY_KB_LARGE_DOC_RAPTOR_ENABLED: "true"
        if _parse_bool_setting(
            m.get(KEY_KB_LARGE_DOC_RAPTOR_ENABLED, DEFAULTS[KEY_KB_LARGE_DOC_RAPTOR_ENABLED])
        )
        else "false",
        "kb_extract_insavlo_enabled": "true" if _parse_bool_setting(insavlo_enabled_raw) else "false",
        "kb_extract_insavlo_base_url": str(
            m.get(KEY_KB_EXTRACT_INSAVLO_BASE_URL, DEFAULTS[KEY_KB_EXTRACT_INSAVLO_BASE_URL])
        ).strip().rstrip("/"),
        "kb_extract_insavlo_skill_code": str(
            m.get(KEY_KB_EXTRACT_INSAVLO_SKILL_CODE, DEFAULTS[KEY_KB_EXTRACT_INSAVLO_SKILL_CODE])
        ).strip(),
        "kb_extract_insavlo_callback_origin": str(
            m.get(
                KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN,
                DEFAULTS[KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN],
            )
        ).strip().rstrip("/"),
        "kb_extract_insavlo_timeout_minutes": str(
            _parse_kb_extract_insavlo_timeout_minutes(insavlo_timeout_raw)
        ),
        "kb_extract_insavlo_api_key": insavlo_api_key_plain,
        "kb_extract_insavlo_has_api_key": "true" if insavlo_has_api_key else "false",
        "kb_extract_insavlo_has_webhook_secret": "true" if insavlo_has_webhook_secret else "false",
        "kb_extract_insavlo_webhook_secret": insavlo_webhook_secret_plain,
        "kb_ingestion_pipeline_json": str(
            m.get(KEY_KB_INGESTION_PIPELINE_JSON, DEFAULTS[KEY_KB_INGESTION_PIPELINE_JSON])
        ),
        # Admin GET 展示；运行时嵌入走 ollama_config_service._load_ollama_db_values（独立 env 回退）
        "ollama_base_url": str(m.get(KEY_OLLAMA_BASE_URL, DEFAULTS[KEY_OLLAMA_BASE_URL])).strip().rstrip("/"),
        "ollama_embed_model": str(m.get(KEY_OLLAMA_EMBED_MODEL, DEFAULTS[KEY_OLLAMA_EMBED_MODEL])).strip(),
        "ollama_embed_dim": str(_parse_ollama_embed_dim(m.get(KEY_OLLAMA_EMBED_DIM, DEFAULTS[KEY_OLLAMA_EMBED_DIM]))),
        "ollama_chat_model": str(m.get(KEY_OLLAMA_CHAT_MODEL, DEFAULTS[KEY_OLLAMA_CHAT_MODEL])).strip(),
        "ollama_timeout_sec": str(_parse_ollama_timeout_sec(m.get(KEY_OLLAMA_TIMEOUT_SEC, DEFAULTS[KEY_OLLAMA_TIMEOUT_SEC]))),
        "ollama_embed_batch_size": str(
            _parse_ollama_embed_batch_size(m.get(KEY_OLLAMA_EMBED_BATCH_SIZE, DEFAULTS[KEY_OLLAMA_EMBED_BATCH_SIZE]))
        ),
        "ollama_num_parallel": str(
            _parse_ollama_num_parallel(m.get(KEY_OLLAMA_NUM_PARALLEL, DEFAULTS[KEY_OLLAMA_NUM_PARALLEL]))
        ),
        "ollama_embed_concurrency": str(
            _parse_ollama_embed_concurrency(m.get(KEY_OLLAMA_EMBED_CONCURRENCY, DEFAULTS[KEY_OLLAMA_EMBED_CONCURRENCY]))
        ),
        "ollama_api_key": ollama_api_key_plain,
        "ollama_has_api_key": "true" if ollama_has_api_key else "false",
        "kb_post_llm_provider": _parse_kb_post_llm_provider(
            m.get(KEY_KB_POST_LLM_PROVIDER, DEFAULTS[KEY_KB_POST_LLM_PROVIDER])
        ),
        "kb_post_llm_base_url": str(
            m.get(KEY_KB_POST_LLM_BASE_URL, DEFAULTS[KEY_KB_POST_LLM_BASE_URL])
        ).strip().rstrip("/"),
        # 管理员系统参数页需要在保存后回显该凭证；运行日志仍不得记录明文。
        "kb_post_llm_api_key": kb_post_llm_api_key_plain,
        "kb_post_llm_has_api_key": "true" if kb_post_llm_has_api_key else "false",
        "kb_post_llm_model": str(
            m.get(KEY_KB_POST_LLM_MODEL, DEFAULTS[KEY_KB_POST_LLM_MODEL])
        ).strip(),
        "kb_post_llm_timeout_sec": str(
            _parse_kb_post_llm_timeout_sec(
                m.get(KEY_KB_POST_LLM_TIMEOUT_SEC, DEFAULTS[KEY_KB_POST_LLM_TIMEOUT_SEC])
            )
        ),
        "kb_post_llm_json_mode": _parse_kb_post_llm_json_mode(
            m.get(KEY_KB_POST_LLM_JSON_MODE, DEFAULTS[KEY_KB_POST_LLM_JSON_MODE])
        ),
        "kb_ragas_llm_provider": _parse_kb_ragas_llm_provider(
            m.get(KEY_KB_RAGAS_LLM_PROVIDER, DEFAULTS[KEY_KB_RAGAS_LLM_PROVIDER])
        ),
        "kb_ragas_llm_base_url": str(
            m.get(KEY_KB_RAGAS_LLM_BASE_URL, DEFAULTS[KEY_KB_RAGAS_LLM_BASE_URL])
        ).strip().rstrip("/"),
        # 与嵌入模型配置中的 Ollama API Key 一致：管理员页面保存后回显明文，
        # 运行时日志仍不得记录明文。
        "kb_ragas_llm_api_key": kb_ragas_llm_api_key_plain,
        "kb_ragas_llm_has_api_key": "true" if kb_ragas_llm_has_api_key else "false",
        "kb_ragas_llm_model": str(
            m.get(KEY_KB_RAGAS_LLM_MODEL, DEFAULTS[KEY_KB_RAGAS_LLM_MODEL])
        ).strip(),
        "kb_ragas_llm_timeout_seconds": str(
            _parse_ragas_bounded_int(
                m.get(KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS, DEFAULTS[KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS]),
                key=KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS,
                minimum=KB_RAGAS_LLM_TIMEOUT_SECONDS_MIN,
                maximum=KB_RAGAS_LLM_TIMEOUT_SECONDS_MAX,
            )
        ),
        "kb_ragas_eval_concurrency": str(
            _parse_ragas_bounded_int(
                m.get(KEY_KB_RAGAS_EVAL_CONCURRENCY, DEFAULTS[KEY_KB_RAGAS_EVAL_CONCURRENCY]),
                key=KEY_KB_RAGAS_EVAL_CONCURRENCY,
                minimum=KB_RAGAS_EVAL_CONCURRENCY_MIN,
                maximum=KB_RAGAS_EVAL_CONCURRENCY_MAX,
            )
        ),
        "kb_ragas_eval_context_max_count": str(
            _parse_ragas_bounded_int(
                m.get(KEY_KB_RAGAS_EVAL_CONTEXT_MAX_COUNT, DEFAULTS[KEY_KB_RAGAS_EVAL_CONTEXT_MAX_COUNT]),
                key=KEY_KB_RAGAS_EVAL_CONTEXT_MAX_COUNT,
                minimum=KB_RAGAS_EVAL_CONTEXT_MAX_COUNT_MIN,
                maximum=KB_RAGAS_EVAL_CONTEXT_MAX_COUNT_MAX,
            )
        ),
        "kb_ragas_eval_context_max_chars_per_item": str(
            _parse_ragas_bounded_int(
                m.get(
                    KEY_KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM,
                    DEFAULTS[KEY_KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM],
                ),
                key=KEY_KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM,
                minimum=KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM_MIN,
                maximum=KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM_MAX,
            )
        ),
        "kb_ragas_eval_context_max_total_chars": str(
            _parse_ragas_bounded_int(
                m.get(
                    KEY_KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS,
                    DEFAULTS[KEY_KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS],
                ),
                key=KEY_KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS,
                minimum=KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS_MIN,
                maximum=KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS_MAX,
            )
        ),
        "mineru_min_batch_mode": _parse_mineru_batch_mode(
            m.get(KEY_MINERU_MIN_BATCH_MODE, DEFAULTS[KEY_MINERU_MIN_BATCH_MODE])
        ),
        "mineru_min_batch_inference_size": str(
            _parse_mineru_batch_size(m.get(KEY_MINERU_MIN_BATCH_INFERENCE_SIZE, DEFAULTS[KEY_MINERU_MIN_BATCH_INFERENCE_SIZE]))
        ),
        "mineru_min_batch_floor": str(
            _parse_mineru_batch_floor(m.get(KEY_MINERU_MIN_BATCH_FLOOR, DEFAULTS[KEY_MINERU_MIN_BATCH_FLOOR]))
        ),
        "mineru_parse_method": _parse_mineru_parse_method(
            m.get(KEY_MINERU_PARSE_METHOD, DEFAULTS[KEY_MINERU_PARSE_METHOD])
        ),
        "mineru_formula_enable": "true"
        if _parse_bool_setting(m.get(KEY_MINERU_FORMULA_ENABLE, DEFAULTS[KEY_MINERU_FORMULA_ENABLE]))
        else "false",
        "mineru_table_enable": "true"
        if _parse_bool_setting(m.get(KEY_MINERU_TABLE_ENABLE, DEFAULTS[KEY_MINERU_TABLE_ENABLE]))
        else "false",
        "mineru_parse_timeout_sec": str(
            _parse_mineru_parse_timeout_sec(m.get(KEY_MINERU_PARSE_TIMEOUT_SEC, DEFAULTS[KEY_MINERU_PARSE_TIMEOUT_SEC]))
        ),
        "mineru_rpc_timeout_sec": str(
            _parse_mineru_rpc_timeout_sec(m.get(KEY_MINERU_RPC_TIMEOUT_SEC, DEFAULTS[KEY_MINERU_RPC_TIMEOUT_SEC]))
        ),
        "mineru_page_chunk_enabled": "true"
        if _parse_bool_setting(m.get(KEY_MINERU_PAGE_CHUNK_ENABLED, DEFAULTS[KEY_MINERU_PAGE_CHUNK_ENABLED]))
        else "false",
        "mineru_page_chunk_threshold": str(
            _parse_mineru_page_chunk_threshold(
                m.get(KEY_MINERU_PAGE_CHUNK_THRESHOLD, DEFAULTS[KEY_MINERU_PAGE_CHUNK_THRESHOLD])
            )
        ),
        "mineru_page_chunk_pages": str(
            _parse_mineru_page_chunk_pages(m.get(KEY_MINERU_PAGE_CHUNK_PAGES, DEFAULTS[KEY_MINERU_PAGE_CHUNK_PAGES]))
        ),
        "mineru_table_auto_rotate": "true"
        if _parse_bool_setting(m.get(KEY_MINERU_TABLE_AUTO_ROTATE, DEFAULTS[KEY_MINERU_TABLE_AUTO_ROTATE]))
        else "false",
        "mineru_table_rotate_max_tables": str(
            _parse_mineru_table_rotate_max_tables(
                m.get(KEY_MINERU_TABLE_ROTATE_MAX_TABLES, DEFAULTS[KEY_MINERU_TABLE_ROTATE_MAX_TABLES])
            )
        ),
        "mineru_table_rotate_timeout_sec": str(
            _parse_mineru_table_rotate_timeout_sec(
                m.get(KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC, DEFAULTS[KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC])
            )
        ),
        "kb_ragas_online_eval_enabled": "true"
        if _parse_bool_setting(m.get(KEY_KB_RAGAS_ONLINE_EVAL_ENABLED, DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_ENABLED]))
        else "false",
        "kb_ragas_online_eval_sample_rate": str(m.get(KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE, DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_SAMPLE_RATE])),
        "kb_ragas_online_eval_timeout_seconds": str(m.get(KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS, DEFAULTS[KEY_KB_RAGAS_ONLINE_EVAL_TIMEOUT_SECONDS])),
        "agent_skill_install_prompt": m.get(KEY_AGENT_SKILL_INSTALL_PROMPT, DEFAULTS[KEY_AGENT_SKILL_INSTALL_PROMPT]),
    }
    try:
        from services.insavlo_config_service import is_insavlo_runtime_ready

        loaded["kb_extract_insavlo_ready"] = "true" if is_insavlo_runtime_ready(db, public_settings=loaded) else "false"
    except Exception:
        loaded["kb_extract_insavlo_ready"] = "false"
    return loaded


def invalidate_settings_cache() -> None:
    global _settings_cache, _kb_index_max_attempts_cache
    with _cache_lock:
        _settings_cache = None
        _kb_index_max_attempts_cache = None


def invalidate_all_settings_caches(*, broadcast: bool = True) -> None:
    """Clear in-process settings/runtime caches; optionally fanout to worker containers."""
    invalidate_settings_cache()
    from services.mineru_config_service import invalidate_mineru_runtime_cache
    from services.ollama_config_service import invalidate_ollama_runtime_cache
    from services.kb_post_llm_service import invalidate_kb_post_llm_runtime_cache
    from services.kb_ragas_llm_service import invalidate_ragas_llm_runtime_cache
    from services.kb_eval_service import invalidate_ragas_eval_runtime_cache

    invalidate_ollama_runtime_cache()
    invalidate_mineru_runtime_cache()
    invalidate_kb_post_llm_runtime_cache()
    invalidate_ragas_llm_runtime_cache()
    invalidate_ragas_eval_runtime_cache()
    from services.pdf_inspector_switch_service import invalidate_pdf_inspector_switch_cache

    invalidate_pdf_inspector_switch_cache()
    # Invalidate agent skill install prompt Redis cache
    from utils.redis_client import get_redis, AGENT_SKILL_INSTALL_PROMPT_KEY
    client = get_redis()
    if client is not None:
        try:
            client.delete(AGENT_SKILL_INSTALL_PROMPT_KEY)
        except Exception:
            pass
    if broadcast:
        from messaging.settings_invalidate_publisher import publish_settings_cache_invalidate

        publish_settings_cache_invalidate()


def migrate_insavlo_timeout_hours_to_minutes(db: Session) -> bool:
    """063: one-time hours→minutes migration under advisory lock 900063."""
    from sqlalchemy import text

    from models.system_setting import SystemSetting

    got = db.execute(
        text("SELECT pg_try_advisory_lock(:k)"), {"k": INSAVLO_TIMEOUT_MIGRATION_LOCK_KEY}
    ).scalar()
    if not got:
        return False
    try:
        new_row = (
            db.query(SystemSetting)
            .filter(SystemSetting.setting_key == KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES)
            .first()
        )
        old_row = (
            db.query(SystemSetting)
            .filter(SystemSetting.setting_key == KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS)
            .first()
        )
        if new_row is not None:
            if old_row is not None:
                db.delete(old_row)
                db.commit()
                invalidate_settings_cache()
            return True
        if old_row is None:
            return True
        try:
            hours = int(str(old_row.value).strip())
        except ValueError:
            hours = int(DEFAULTS[KEY_KB_EXTRACT_INSAVLO_TIMEOUT_HOURS])
        minutes = max(
            KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MIN,
            min(KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MAX, hours * 60),
        )
        db.add(
            SystemSetting(
                setting_key=KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES,
                value=str(minutes),
            )
        )
        db.delete(old_row)
        db.commit()
        invalidate_settings_cache()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute(
            text("SELECT pg_advisory_unlock(:k)"), {"k": INSAVLO_TIMEOUT_MIGRATION_LOCK_KEY}
        )


def get_fresh_public_settings_dict(db: Session) -> dict[str, str]:
    """Load system settings from DB, bypassing the in-process cache.

    Use for cross-process consumers (e.g. kb-extract) that must not rely on
    cache invalidation from the API process after admin saves settings.
    """
    return _load_from_db(db)


def get_public_settings_dict(db: Session) -> dict[str, str]:
    global _settings_cache
    ensure_mineru_settings_defaults(db)
    with _cache_lock:
        if _settings_cache is not None:
            return dict(_settings_cache)
    loaded = _load_from_db(db)
    with _cache_lock:
        if _settings_cache is None:
            _settings_cache = loaded
        return dict(_settings_cache)


def _settings_dict(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> dict[str, str]:
    """Merge system settings with optional per-user effective overrides."""
    system = get_public_settings_dict(db)
    if effective is not None:
        merged = dict(system)
        merged.update(effective)
        return merged
    if user_id is not None:
        from services.user_setting_service import get_user_effective_dict

        merged = dict(system)
        merged.update(get_user_effective_dict(db, user_id))
        return merged
    return system


CLIENT_SETTINGS_KEYS: tuple[str, ...] = (
    "clipboard_prefix",
    "clipboard_suffix",
    "tag_graph_single_node_symbol_size",
    "tag_graph_node_display_ratio",
    "tag_graph_edge_line_width",
    "tag_graph_enabled",
    "max_upload_size_mb",
    "shared_workspaces_enabled",
    "kb_extract_provider",
    "kb_extract_insavlo_ready",
    "kb_search_default_top_k",
    "kb_voice_notify_enabled",
    "kb_voice_notify_playback_ttl_seconds",
    "kb_sag_event_extract_enabled",
)


def get_client_settings_dict(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> dict[str, str]:
    """登录用户 Web 端可见的系统参数子集（不含检索/索引/Wiki 运维项）。"""
    full = _settings_dict(db, user_id=user_id, effective=effective)
    return {k: full[k] for k in CLIENT_SETTINGS_KEYS}



def validate_and_normalize_setting(key: str, raw: object) -> str:
    """Validate and normalize a single system/user setting value."""
    if key not in KNOWN_KEYS:
        raise ValueError(f"未知参数: {key}")
    if isinstance(raw, bool):
        raw = "true" if raw else "false"
    raw = str(raw)
    if key in (KEY_CLIPBOARD_PREFIX, KEY_CLIPBOARD_SUFFIX):
        if len(raw) > MAX_PREFIX_SUFFIX_LEN:
            raise ValueError(f"{key} 长度不能超过 {MAX_PREFIX_SUFFIX_LEN}")
    if key == KEY_TAG_GRAPH_SINGLE:
        try:
            n = int(str(raw).strip())
        except ValueError as e:
            raise ValueError("tag_graph_single_node_symbol_size 须为整数") from e
        if not (TAG_GRAPH_SINGLE_MIN <= n <= TAG_GRAPH_SINGLE_MAX):
            raise ValueError(
                f"tag_graph_single_node_symbol_size 须在 {TAG_GRAPH_SINGLE_MIN}–{TAG_GRAPH_SINGLE_MAX} 之间"
            )
        raw = str(n)
    if key == KEY_TAG_GRAPH_NODE_DISPLAY_RATIO:
        try:
            n = float(str(raw).strip())
        except ValueError as e:
            raise ValueError("tag_graph_node_display_ratio 须为数字") from e
        if not (TAG_GRAPH_NODE_DISPLAY_RATIO_MIN <= n <= TAG_GRAPH_NODE_DISPLAY_RATIO_MAX):
            raise ValueError(
                f"tag_graph_node_display_ratio 须在 {TAG_GRAPH_NODE_DISPLAY_RATIO_MIN}–{TAG_GRAPH_NODE_DISPLAY_RATIO_MAX} 之间"
            )
        raw = str(_parse_tag_graph_node_display_ratio(str(n)))
    if key == KEY_TAG_GRAPH_EDGE_LINE_WIDTH:
        try:
            n = int(str(raw).strip())
        except ValueError as e:
            raise ValueError("tag_graph_edge_line_width 须为整数") from e
        if not (TAG_GRAPH_EDGE_LINE_WIDTH_MIN <= n <= TAG_GRAPH_EDGE_LINE_WIDTH_MAX):
            raise ValueError(
                f"tag_graph_edge_line_width 须在 {TAG_GRAPH_EDGE_LINE_WIDTH_MIN}–{TAG_GRAPH_EDGE_LINE_WIDTH_MAX} 之间"
            )
        raw = str(n)
    if key == KEY_TAG_GRAPH_ENABLED:
        raw_lower = str(raw).strip().lower()
        if raw_lower in ("true", "1", "yes", "on"):
            raw = "true"
        elif raw_lower in ("false", "0", "no", "off"):
            raw = "false"
        else:
            raise ValueError("tag_graph_enabled 须为 true 或 false")
    if key == KEY_MAX_UPLOAD_SIZE_MB:
        try:
            n = int(str(raw).strip())
        except ValueError as e:
            raise ValueError("max_upload_size_mb 须为整数") from e
        if not (MAX_UPLOAD_SIZE_MB_MIN <= n <= MAX_UPLOAD_SIZE_MB_MAX):
            raise ValueError(
                f"max_upload_size_mb 须在 {MAX_UPLOAD_SIZE_MB_MIN}–{MAX_UPLOAD_SIZE_MB_MAX} 之间（单位 MB）"
            )
        raw = str(n)
    if key == KEY_WORKSPACE_BACKUP_MAX_MB:
        try:
            n = int(str(raw).strip())
        except ValueError as e:
            raise ValueError("workspace_backup_max_mb 须为整数") from e
        if not (WORKSPACE_BACKUP_MAX_MB_MIN <= n <= WORKSPACE_BACKUP_MAX_MB_MAX):
            raise ValueError(
                f"workspace_backup_max_mb 须在 {WORKSPACE_BACKUP_MAX_MB_MIN}–"
                f"{WORKSPACE_BACKUP_MAX_MB_MAX} 之间（单位 MB）"
            )
        raw = str(n)
    if key == KEY_KB_INDEX_MAX_ATTEMPTS:
        try:
            n = int(str(raw).strip())
        except ValueError as e:
            raise ValueError("kb_index_max_attempts 须为整数") from e
        if not (KB_INDEX_MAX_ATTEMPTS_MIN <= n <= KB_INDEX_MAX_ATTEMPTS_MAX):
            raise ValueError(
                f"kb_index_max_attempts 须在 {KB_INDEX_MAX_ATTEMPTS_MIN}–{KB_INDEX_MAX_ATTEMPTS_MAX} 之间"
            )
        raw = str(n)
    if key == KEY_KB_POST_MAX_ATTEMPTS:
        try:
            n = int(str(raw).strip())
        except ValueError as e:
            raise ValueError("kb_post_max_attempts 须为整数") from e
        if not (KB_POST_MAX_ATTEMPTS_MIN <= n <= KB_POST_MAX_ATTEMPTS_MAX):
            raise ValueError(
                f"kb_post_max_attempts 须在 {KB_POST_MAX_ATTEMPTS_MIN}–{KB_POST_MAX_ATTEMPTS_MAX} 之间"
            )
        raw = str(n)
    if key == KEY_KB_POST_ASYNC_ENABLED:
        raw_lower = str(raw).strip().lower()
        if raw_lower in ("true", "1", "yes", "on"):
            raw = "true"
        elif raw_lower in ("false", "0", "no", "off"):
            raw = "false"
        else:
            raise ValueError("kb_post_async_enabled 须为 true 或 false")
    if key == KEY_AGENT_RUN_RETENTION_DAYS:
        try:
            n = int(str(raw).strip())
        except ValueError as e:
            raise ValueError("agent_run_retention_days 须为整数") from e
        if not (AGENT_RUN_RETENTION_DAYS_MIN <= n <= AGENT_RUN_RETENTION_DAYS_MAX):
            raise ValueError(
                f"agent_run_retention_days 须在 {AGENT_RUN_RETENTION_DAYS_MIN}–"
                f"{AGENT_RUN_RETENTION_DAYS_MAX} 之间"
            )
        raw = str(n)
    if key == KEY_SHARED_WORKSPACES_ENABLED:
        raw_lower = str(raw).strip().lower()
        if raw_lower in ("true", "1", "yes", "on"):
            raw = "true"
        elif raw_lower in ("false", "0", "no", "off"):
            raw = "false"
        else:
            raise ValueError("shared_workspaces_enabled 须为 true 或 false")
    if key == KEY_ENTERPRISE_RBAC_ENABLED:
        raw_lower = str(raw).strip().lower()
        if raw_lower in ("true", "1", "yes", "on"):
            raw = "true"
        elif raw_lower in ("false", "0", "no", "off"):
            raw = "false"
        else:
            raise ValueError("enterprise_rbac_enabled 须为 true 或 false")
    if key == KEY_ENTERPRISE_RBAC_CUTOVER:
        raw_lower = str(raw).strip().lower()
        if raw_lower in ("true", "1", "yes", "on"):
            raw = "true"
        elif raw_lower in ("false", "0", "no", "off"):
            raw = "false"
        else:
            raise ValueError("enterprise_rbac_cutover 须为 true 或 false")
    if key == KEY_ENTERPRISE_RBAC_WRITE_MODE:
        mode = _parse_enterprise_rbac_write_mode(str(raw))
        if mode not in ("dual", "new_only"):
            raise ValueError("enterprise_rbac_write_mode 须为 dual 或 new_only")
        raw = mode
    if key == KEY_KB_SEARCH_HYBRID_ENABLED:
        raw_lower = str(raw).strip().lower()
        if raw_lower in ("true", "1", "yes", "on"):
            raw = "true"
        elif raw_lower in ("false", "0", "no", "off"):
            raw = "false"
        else:
            raise ValueError("kb_search_hybrid_enabled 须为 true 或 false")
    if key == KEY_KB_SEARCH_TAG_COOC_ENABLED:
        raw_lower = str(raw).strip().lower()
        if raw_lower in ("true", "1", "yes", "on"):
            raw = "true"
        elif raw_lower in ("false", "0", "no", "off"):
            raw = "false"
        else:
            raise ValueError("kb_search_tag_cooc_enabled 须为 true 或 false")
    if key == KEY_KB_SEARCH_TAG_COOC_MIN_EDGE:
        try:
            n = int(str(raw).strip())
        except ValueError as e:
            raise ValueError("kb_search_tag_cooc_min_edge 须为整数") from e
        if n < 1:
            raise ValueError("kb_search_tag_cooc_min_edge 须 ≥ 1")
        raw = str(n)
    if key == KEY_KB_CHUNK_PROFILE:
        raw = _parse_kb_chunk_profile(str(raw))
    if key == KEY_KB_CHUNK_SIZE:
        raw = _normalize_kb_chunk_size(str(raw))
    if key == KEY_KB_CHUNK_OVERLAP:
        raw = _normalize_kb_chunk_overlap(str(raw))
    if key == KEY_KB_CHUNK_SPLIT_RECURSIVE:
        raw = "true" if _parse_bool_setting(str(raw)) else "false"
    if key == KEY_KB_EMBED_CACHE_ENABLED:
        raw = "true" if _parse_kb_embed_cache_enabled(str(raw)) else "false"
    if key == KEY_KB_EXTRACT_PROVIDER:
        raw = _parse_kb_extract_provider(str(raw))
    if key == KEY_KB_SEARCH_DEFAULT_TOP_K:
        try:
            n = int(str(raw).strip())
        except ValueError as e:
            raise ValueError("kb_search_default_top_k 须为整数") from e
        if not (KB_SEARCH_DEFAULT_TOP_K_MIN <= n <= KB_SEARCH_DEFAULT_TOP_K_MAX):
            raise ValueError(
                f"kb_search_default_top_k 须在 {KB_SEARCH_DEFAULT_TOP_K_MIN}–{KB_SEARCH_DEFAULT_TOP_K_MAX} 之间"
            )
        raw = str(_parse_kb_search_default_top_k(str(n)))
    if key == KEY_KB_SEARCH_MIN_SCORE:
        try:
            n = float(str(raw).strip())
        except ValueError as e:
            raise ValueError("kb_search_min_score 须为数字") from e
        if not (KB_SEARCH_MIN_SCORE_MIN <= n <= KB_SEARCH_MIN_SCORE_MAX):
            raise ValueError(
                f"kb_search_min_score 须在 {KB_SEARCH_MIN_SCORE_MIN}–{KB_SEARCH_MIN_SCORE_MAX} 之间（0 表示关闭）"
            )
        raw = str(_parse_kb_search_min_score(str(n)))
    if key == KEY_KB_SEARCH_BOOST_KEYWORD_BONUS:
        try:
            n = float(str(raw).strip())
        except ValueError as e:
            raise ValueError("kb_search_boost_keyword_bonus 须为数字") from e
        if not (KB_SEARCH_BOOST_KEYWORD_BONUS_MIN <= n <= KB_SEARCH_BOOST_KEYWORD_BONUS_MAX):
            raise ValueError(
                f"kb_search_boost_keyword_bonus 须在 {KB_SEARCH_BOOST_KEYWORD_BONUS_MIN}–{KB_SEARCH_BOOST_KEYWORD_BONUS_MAX} 之间"
            )
        raw = str(_parse_kb_search_boost_keyword_bonus(str(n)))
    if key == KEY_KB_SEARCH_MODALITY_BOOST:
        try:
            n = float(str(raw).strip())
        except ValueError as e:
            raise ValueError("kb_search_modality_boost 须为数字") from e
        if not (KB_SEARCH_MODALITY_BOOST_MIN <= n <= KB_SEARCH_MODALITY_BOOST_MAX):
            raise ValueError(
                f"kb_search_modality_boost 须在 {KB_SEARCH_MODALITY_BOOST_MIN}–{KB_SEARCH_MODALITY_BOOST_MAX} 之间（0 表示关闭）"
            )
        raw = str(_parse_kb_search_modality_boost(str(n)))
    if key == KEY_KB_SEARCH_MODALITY_BOOST_ENABLED:
        raw = "true" if _parse_bool_setting(str(raw)) else "false"
    if key == KEY_KB_VOICE_NOTIFY_ENABLED:
        raw_lower = str(raw).strip().lower()
        if raw_lower in ("true", "1", "yes", "on"):
            raw = "true"
        elif raw_lower in ("false", "0", "no", "off"):
            raw = "false"
        else:
            raise ValueError("kb_voice_notify_enabled 须为 true 或 false")
    if key == KEY_KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS:
        try:
            n = int(str(raw).strip())
        except ValueError as e:
            raise ValueError("kb_voice_notify_playback_ttl_seconds 须为整数") from e
        if not (
            KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS_MIN
            <= n
            <= KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS_MAX
        ):
            raise ValueError(
                "kb_voice_notify_playback_ttl_seconds 须在 "
                f"{KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS_MIN}–{KB_VOICE_NOTIFY_PLAYBACK_TTL_SECONDS_MAX} 之间"
            )
        raw = str(_parse_kb_voice_notify_playback_ttl_seconds(str(n)))
    if key == KEY_KB_SEARCH_FILENAME_BOOST:
        try:
            n = float(str(raw).strip())
        except ValueError as e:
            raise ValueError("kb_search_filename_boost 须为数字") from e
        if not (KB_SEARCH_FILENAME_BOOST_MIN <= n <= KB_SEARCH_FILENAME_BOOST_MAX):
            raise ValueError(
                f"kb_search_filename_boost 须在 {KB_SEARCH_FILENAME_BOOST_MIN}–{KB_SEARCH_FILENAME_BOOST_MAX} 之间（0 表示关闭）"
            )
        raw = str(_parse_kb_search_filename_boost(str(n)))
    if key == KEY_KB_SEARCH_MMR_LAMBDA:
        try:
            n = float(str(raw).strip())
        except ValueError as e:
            raise ValueError("kb_search_mmr_lambda 须为数字") from e
        if not (KB_SEARCH_MMR_LAMBDA_MIN <= n <= KB_SEARCH_MMR_LAMBDA_MAX):
            raise ValueError(
                f"kb_search_mmr_lambda 须在 {KB_SEARCH_MMR_LAMBDA_MIN}–{KB_SEARCH_MMR_LAMBDA_MAX} 之间（0 表示关闭 MMR）"
            )
        raw = str(_parse_kb_search_mmr_lambda(str(n)))
    if key == KEY_KB_FTS_CONFIG:
        raw = _parse_kb_fts_config(str(raw))
    if key == KEY_KB_WIKI_LINT_INTERVAL_HOURS:
        raw = str(_parse_kb_wiki_lint_interval_hours(str(raw)))
    if key == KEY_KB_WIKI_COMPILE_MIN_SOURCES:
        raw = str(_parse_kb_wiki_compile_min_sources(str(raw)))
    if key == KEY_KB_ENTITY_EXTRACT_ENABLED:
        raw = "true" if _parse_bool_setting(str(raw)) else "false"
    if key == KEY_KB_SAG_EVENT_EXTRACT_ENABLED:
        raw = "true" if _parse_bool_setting(str(raw)) else "false"
    if key == KEY_KB_SAG_EVENT_EMBED_ENABLED:
        raw = "true" if _parse_bool_setting(str(raw)) else "false"
    if key == KEY_KB_SAG_EVENT_EXTRACT_MODE:
        raw = _parse_kb_sag_event_extract_mode(str(raw))
    if key == KEY_KB_SAG_EVENT_PROMPT_VERSION:
        raw = str(_parse_kb_sag_event_prompt_version(str(raw)))
    if key == KEY_KB_SAG_QUERY_LLM_ENABLED:
        raw = "true" if _parse_bool_setting(str(raw)) else "false"
    if key == KEY_KB_EXTRACT_INSAVLO_ENABLED:
        raw_lower = str(raw).strip().lower()
        if raw_lower in ("true", "1", "yes", "on"):
            raw = "true"
        elif raw_lower in ("false", "0", "no", "off"):
            raw = "false"
        else:
            raise ValueError("kb_extract_insavlo_enabled 须为 true 或 false")
    if key == KEY_KB_PDF_INSPECTOR_ENABLED:
        raw_lower = str(raw).strip().lower()
        if raw_lower in ("true", "1", "yes", "on"):
            raw = "true"
        elif raw_lower in ("false", "0", "no", "off"):
            raw = "false"
        else:
            raise ValueError("kb_pdf_inspector_enabled 须为 true 或 false")
    if key in (KEY_KB_EXTRACT_INSAVLO_BASE_URL, KEY_KB_EXTRACT_INSAVLO_CALLBACK_ORIGIN):
        raw = str(raw).strip().rstrip("/")
    if key == KEY_KB_EXTRACT_INSAVLO_SKILL_CODE:
        raw = str(raw).strip()
    if key == KEY_KB_INGESTION_PIPELINE_JSON:
        raw_str = str(raw).strip()
        if raw_str:
            from services.kb_pipeline_service import parse_pipeline_config, serialize_pipeline_config

            config = parse_pipeline_config(raw_str)
            raw = serialize_pipeline_config(config) if config else ""
        else:
            raw = ""
    if key == KEY_KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES:
        try:
            n = int(str(raw).strip())
        except ValueError as e:
            raise ValueError("kb_extract_insavlo_timeout_minutes 须为整数") from e
        if not (KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MIN <= n <= KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MAX):
            raise ValueError(
                "kb_extract_insavlo_timeout_minutes 须在 "
                f"{KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MIN}–{KB_EXTRACT_INSAVLO_TIMEOUT_MINUTES_MAX} 之间"
            )
        raw = str(n)
    if key == KEY_OLLAMA_BASE_URL:
        from services.ollama_config_service import validate_ollama_base_url

        raw = validate_ollama_base_url(str(raw))
    if key == KEY_OLLAMA_EMBED_MODEL:
        raw = str(raw).strip()
        if not raw:
            raise ValueError("ollama_embed_model 不能为空")
    if key == KEY_OLLAMA_CHAT_MODEL:
        raw = str(raw).strip()
        if not raw:
            raise ValueError("ollama_chat_model 不能为空")
    if key == KEY_OLLAMA_EMBED_DIM:
        raw = str(_parse_ollama_embed_dim(str(raw)))
    if key == KEY_OLLAMA_TIMEOUT_SEC:
        raw = str(_parse_ollama_timeout_sec(str(raw)))
    if key == KEY_OLLAMA_EMBED_BATCH_SIZE:
        raw = str(_parse_ollama_embed_batch_size(str(raw)))
    if key == KEY_OLLAMA_NUM_PARALLEL:
        raw = str(_parse_ollama_num_parallel(str(raw)))
    if key == KEY_OLLAMA_EMBED_CONCURRENCY:
        raw = str(_parse_ollama_embed_concurrency(str(raw)))
    if key == KEY_OLLAMA_API_KEY:
        raw = str(raw).strip()
    if key == KEY_KB_POST_LLM_PROVIDER:
        raw = _parse_kb_post_llm_provider(str(raw))
    if key == KEY_KB_POST_LLM_BASE_URL:
        raw = _validate_openai_compatible_base_url(str(raw))
    if key == KEY_KB_POST_LLM_API_KEY:
        raw = str(raw).strip()
    if key == KEY_KB_POST_LLM_MODEL:
        raw = str(raw).strip()
    if key == KEY_KB_POST_LLM_TIMEOUT_SEC:
        raw = str(_parse_kb_post_llm_timeout_sec(str(raw)))
    if key == KEY_KB_POST_LLM_JSON_MODE:
        raw = _parse_kb_post_llm_json_mode(str(raw))
    if key == KEY_KB_RAGAS_LLM_PROVIDER:
        raw = _parse_kb_ragas_llm_provider(str(raw))
    if key == KEY_KB_RAGAS_LLM_BASE_URL:
        raw = _validate_ragas_llm_base_url(str(raw))
    if key == KEY_KB_RAGAS_LLM_API_KEY:
        raw = str(raw).strip()
    if key == KEY_KB_RAGAS_LLM_MODEL:
        raw = str(raw).strip()
        if not raw:
            raise ValueError("kb_ragas_llm_model 不能为空")
    if key == KEY_KB_RAGAS_LLM_TIMEOUT_SECONDS:
        raw = str(_parse_ragas_bounded_int(
            str(raw), key=key, minimum=KB_RAGAS_LLM_TIMEOUT_SECONDS_MIN, maximum=KB_RAGAS_LLM_TIMEOUT_SECONDS_MAX
        ))
    if key == KEY_KB_RAGAS_EVAL_CONCURRENCY:
        raw = str(_parse_ragas_bounded_int(
            str(raw), key=key, minimum=KB_RAGAS_EVAL_CONCURRENCY_MIN, maximum=KB_RAGAS_EVAL_CONCURRENCY_MAX
        ))
    if key == KEY_KB_RAGAS_EVAL_CONTEXT_MAX_COUNT:
        raw = str(_parse_ragas_bounded_int(
            str(raw), key=key, minimum=KB_RAGAS_EVAL_CONTEXT_MAX_COUNT_MIN, maximum=KB_RAGAS_EVAL_CONTEXT_MAX_COUNT_MAX
        ))
    if key == KEY_KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM:
        raw = str(_parse_ragas_bounded_int(
            str(raw), key=key, minimum=KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM_MIN, maximum=KB_RAGAS_EVAL_CONTEXT_MAX_CHARS_PER_ITEM_MAX
        ))
    if key == KEY_KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS:
        raw = str(_parse_ragas_bounded_int(
            str(raw), key=key, minimum=KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS_MIN, maximum=KB_RAGAS_EVAL_CONTEXT_MAX_TOTAL_CHARS_MAX
        ))
    if key == KEY_MINERU_MIN_BATCH_MODE:
        raw = _parse_mineru_batch_mode(str(raw))
    if key == KEY_MINERU_MIN_BATCH_INFERENCE_SIZE:
        raw = str(_parse_mineru_batch_size(str(raw)))
    if key == KEY_MINERU_MIN_BATCH_FLOOR:
        raw = str(_parse_mineru_batch_floor(str(raw)))
    if key == KEY_MINERU_PARSE_METHOD:
        raw = _parse_mineru_parse_method(str(raw))
    if key in (KEY_MINERU_FORMULA_ENABLE, KEY_MINERU_TABLE_ENABLE, KEY_MINERU_PAGE_CHUNK_ENABLED, KEY_MINERU_TABLE_AUTO_ROTATE):
        raw = "true" if _parse_bool_setting(str(raw)) else "false"
    if key in (
        KEY_KB_RAPTOR_ENABLED,
        KEY_KB_RAPTOR_FAIL_OPEN,
        KEY_KB_LARGE_DOC_POST_ENABLED,
        KEY_KB_LARGE_DOC_RAPTOR_ENABLED,
        KEY_KB_MULTI_REPR_ENABLED,
    ):
        raw = "true" if _parse_bool_setting(str(raw)) else "false"
    if key == KEY_KB_RAPTOR_MIN_CHARS:
        raw = str(_parse_kb_raptor_min_chars(str(raw)))
    if key == KEY_KB_RAPTOR_MAX_LEVELS:
        raw = str(_parse_kb_raptor_max_levels(str(raw)))
    if key == KEY_KB_RAPTOR_MAX_SUMMARIES_PER_FILE:
        raw = str(_parse_kb_raptor_max_summaries(str(raw)))
    if key == KEY_KB_RAPTOR_OLLAMA_TIMEOUT_SEC:
        raw = str(_parse_kb_raptor_timeout_sec(str(raw)))
    if key == KEY_KB_RAPTOR_DRILL_K:
        raw = str(_parse_kb_raptor_drill_k(str(raw)))
    if key == KEY_KB_RAPTOR_DRILL_SCORE_FACTOR:
        raw = str(_parse_kb_raptor_drill_score_factor(str(raw)))
    if key == KEY_KB_LARGE_DOC_CHAR_THRESHOLD:
        raw = str(_parse_kb_large_doc_char_threshold(str(raw)))
    if key == KEY_KB_LARGE_DOC_CHUNK_SIZE:
        raw = str(_parse_kb_large_doc_chunk_size(str(raw)))
    if key == KEY_KB_LARGE_DOC_CHUNK_OVERLAP:
        raw = str(_parse_kb_large_doc_chunk_overlap(str(raw)))
    if key == KEY_MINERU_PARSE_TIMEOUT_SEC:
        raw = str(_parse_mineru_parse_timeout_sec(str(raw)))
    if key == KEY_MINERU_RPC_TIMEOUT_SEC:
        raw = str(_parse_mineru_rpc_timeout_sec(str(raw)))
    if key == KEY_MINERU_PAGE_CHUNK_THRESHOLD:
        raw = str(_parse_mineru_page_chunk_threshold(str(raw)))
    if key == KEY_MINERU_PAGE_CHUNK_PAGES:
        raw = str(_parse_mineru_page_chunk_pages(str(raw)))
    if key == KEY_MINERU_TABLE_ROTATE_MAX_TABLES:
        raw = str(_parse_mineru_table_rotate_max_tables(str(raw)))
    if key == KEY_MINERU_TABLE_ROTATE_TIMEOUT_SEC:
        raw = str(_parse_mineru_table_rotate_timeout_sec(str(raw)))
    return raw







def _validate_mineru_batch_combo(db: Session) -> None:
    d = get_public_settings_dict(db)
    floor = _parse_mineru_batch_floor(d.get("mineru_min_batch_floor", DEFAULTS[KEY_MINERU_MIN_BATCH_FLOOR]))
    ceiling = _parse_mineru_batch_size(
        d.get("mineru_min_batch_inference_size", DEFAULTS[KEY_MINERU_MIN_BATCH_INFERENCE_SIZE])
    )
    if floor > ceiling:
        raise ValueError("mineru_min_batch_floor 不能大于 mineru_min_batch_inference_size")


def _validate_kb_chunk_size_overlap_combo(db: Session) -> None:
    from services.kb_chunk_profile import profile_table_chunk_params
    from services.kb_embed_limits import max_chars_for_model
    from services.ollama_config_service import get_ollama_runtime_config

    d = get_public_settings_dict(db)
    size = _parse_optional_positive_int(d.get(KEY_KB_CHUNK_SIZE, DEFAULTS[KEY_KB_CHUNK_SIZE]))
    overlap = _parse_optional_positive_int(d.get(KEY_KB_CHUNK_OVERLAP, DEFAULTS[KEY_KB_CHUNK_OVERLAP]))
    if overlap is None:
        return
    if size is None:
        profile_name = _parse_kb_chunk_profile(d.get(KEY_KB_CHUNK_PROFILE, DEFAULTS[KEY_KB_CHUNK_PROFILE]))
        size, _ = profile_table_chunk_params(profile_name)
    embed_model = get_ollama_runtime_config(db).embed_model
    effective_size = min(size, max_chars_for_model(embed_model))
    if overlap >= effective_size:
        raise ValueError(f"kb_chunk_overlap 须小于 effective chunk size ({effective_size})")

def _validate_rbac_cutover_combo(db: Session) -> None:
    """cutover 仅允许在 RBAC on + new_only 时开启。"""
    m = {r.setting_key: r.value for r in db.query(SystemSetting).filter(SystemSetting.setting_key.in_((
        KEY_ENTERPRISE_RBAC_ENABLED,
        KEY_ENTERPRISE_RBAC_WRITE_MODE,
        KEY_ENTERPRISE_RBAC_CUTOVER,
    ))).all()}
    if not _parse_bool_setting(m.get(KEY_ENTERPRISE_RBAC_CUTOVER, DEFAULTS[KEY_ENTERPRISE_RBAC_CUTOVER])):
        return
    if not _parse_bool_setting(m.get(KEY_ENTERPRISE_RBAC_ENABLED, DEFAULTS[KEY_ENTERPRISE_RBAC_ENABLED])):
        raise ValueError("enterprise_rbac_cutover 须 enterprise_rbac_enabled=true")
    if _parse_enterprise_rbac_write_mode(m.get(KEY_ENTERPRISE_RBAC_WRITE_MODE, DEFAULTS[KEY_ENTERPRISE_RBAC_WRITE_MODE])) != "new_only":
        raise ValueError("enterprise_rbac_cutover 须 enterprise_rbac_write_mode=new_only")


def _enforce_raptor_master_combo(db: Session) -> None:
    """113: kb_raptor_enabled=false 时强制关闭 kb_large_doc_raptor_enabled。"""
    from models.system_setting import SystemSetting

    m = {
        r.setting_key: r.value
        for r in db.query(SystemSetting)
        .filter(
            SystemSetting.setting_key.in_(
                (KEY_KB_RAPTOR_ENABLED, KEY_KB_LARGE_DOC_RAPTOR_ENABLED)
            )
        )
        .all()
    }
    master = _parse_bool_setting(m.get(KEY_KB_RAPTOR_ENABLED, DEFAULTS[KEY_KB_RAPTOR_ENABLED]))
    if master:
        return
    if not _parse_bool_setting(
        m.get(KEY_KB_LARGE_DOC_RAPTOR_ENABLED, DEFAULTS[KEY_KB_LARGE_DOC_RAPTOR_ENABLED])
    ):
        return
    row = _get_or_create_row(db, KEY_KB_LARGE_DOC_RAPTOR_ENABLED)
    row.value = "false"


def _validate_kb_post_llm_combo(db: Session) -> None:
    keys = (
        KEY_KB_POST_LLM_PROVIDER,
        KEY_KB_POST_LLM_BASE_URL,
        KEY_KB_POST_LLM_MODEL,
        KEY_KB_POST_LLM_JSON_MODE,
        KEY_KB_POST_LLM_TIMEOUT_SEC,
    )
    m = {
        row.setting_key: row.value
        for row in db.query(SystemSetting).filter(SystemSetting.setting_key.in_(keys)).all()
    }
    provider = _parse_kb_post_llm_provider(
        m.get(KEY_KB_POST_LLM_PROVIDER, DEFAULTS[KEY_KB_POST_LLM_PROVIDER])
    )
    if provider != "openai_compatible":
        return
    base_url = _validate_openai_compatible_base_url(
        m.get(KEY_KB_POST_LLM_BASE_URL, DEFAULTS[KEY_KB_POST_LLM_BASE_URL])
    )
    model = str(m.get(KEY_KB_POST_LLM_MODEL, DEFAULTS[KEY_KB_POST_LLM_MODEL]) or "").strip()
    if not base_url:
        raise ValueError("kb_post_llm_base_url 不能为空")
    if not model:
        raise ValueError("kb_post_llm_model 不能为空")


def _couple_enterprise_rbac_to_shared(db: Session, updates: dict[str, str]) -> None:
    """Backward-compatible hook retained for callers; RBAC and shared workspace are independent.

    Production S1 keeps shared workspaces enabled while enterprise RBAC remains disabled, so the
    service layer must not rewrite either setting from the other.
    """
    return None


def update_settings(db: Session, updates: dict[str, str], *, commit: bool = True) -> dict[str, str]:
    ensure_mineru_settings_defaults(db)
    for key in updates:
        if key not in KNOWN_KEYS:
            raise ValueError(f"未知参数: {key}")
    _couple_enterprise_rbac_to_shared(db, updates)
    for key, raw in updates.items():
        if key in SKIP_EMPTY_UPDATE_KEYS and str(raw).strip() == "":
            continue
        normalized = validate_and_normalize_setting(key, raw)
        if key in (KEY_KB_EXTRACT_INSAVLO_API_KEY, KEY_KB_EXTRACT_INSAVLO_WEBHOOK_SECRET):
            normalized = insavlo_credential_from_stored(normalized)
        row = _get_or_create_row(db, key)
        row.value = normalized
    db.flush()
    _validate_kb_chunk_size_overlap_combo(db)
    _validate_mineru_batch_combo(db)
    _validate_rbac_cutover_combo(db)
    _enforce_raptor_master_combo(db)
    _validate_kb_post_llm_combo(db)
    if commit:
        db.commit()
        invalidate_all_settings_caches(broadcast=True)
    return get_public_settings_dict(db)


def get_max_upload_bytes(db: Session) -> int:
    d = get_public_settings_dict(db)
    mb = int(str(d["max_upload_size_mb"]).strip())
    return mb * 1024 * 1024


def get_workspace_backup_max_bytes(db: Session) -> int:
    """个人空间整包备份体积上限（字节）：系统参数表优先，环境变量 WORKSPACE_BACKUP_MAX_BYTES 兜底。"""
    from config import WORKSPACE_BACKUP_MAX_BYTES

    row = (
        db.query(SystemSetting)
        .filter(SystemSetting.setting_key == KEY_WORKSPACE_BACKUP_MAX_MB)
        .first()
    )
    if row is not None:
        mb = _parse_workspace_backup_max_mb(row.value)
        return mb * 1024 * 1024
    return WORKSPACE_BACKUP_MAX_BYTES




def _parse_kb_wiki_lint_interval_hours(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return 0
    return max(0, min(168, n))


def get_kb_wiki_lint_interval_hours(db: Session) -> int:
    import os

    env = os.environ.get("KB_WIKI_LINT_INTERVAL_HOURS")
    if env is not None and str(env).strip():
        try:
            return max(0, int(str(env).strip()))
        except ValueError:
            pass
    d = get_public_settings_dict(db)
    return _parse_kb_wiki_lint_interval_hours(
        d.get(KEY_KB_WIKI_LINT_INTERVAL_HOURS, DEFAULTS[KEY_KB_WIKI_LINT_INTERVAL_HOURS])
    )

def _parse_kb_wiki_compile_min_sources(raw: str) -> int:
    try:
        n = int(str(raw).strip())
    except ValueError:
        return 2
    return max(1, min(20, n))


def is_kb_entity_extract_enabled(db: Session) -> bool:
    from config import KB_ENTITY_EXTRACT_ENABLED

    if KB_ENTITY_EXTRACT_ENABLED:
        return True
    d = get_public_settings_dict(db)
    return _parse_bool_setting(
        d.get(KEY_KB_ENTITY_EXTRACT_ENABLED, DEFAULTS[KEY_KB_ENTITY_EXTRACT_ENABLED])
    )


KB_SAG_EVENT_EXTRACT_MODES = frozenset({"rule", "ollama"})


def _parse_kb_sag_event_extract_mode(raw: str) -> str:
    mode = str(raw).strip().lower()
    if mode not in KB_SAG_EVENT_EXTRACT_MODES:
        raise ValueError("kb_sag_event_extract_mode 须为 rule 或 ollama")
    return mode


def _parse_kb_sag_event_prompt_version(raw: str) -> int:
    try:
        version = int(str(raw).strip())
    except ValueError as exc:
        raise ValueError("kb_sag_event_prompt_version 须为整数") from exc
    if not (1 <= version <= 9999):
        raise ValueError("kb_sag_event_prompt_version 须在 1–9999 之间")
    return version


def is_kb_sag_event_extract_enabled(db: Session) -> bool:
    d = get_public_settings_dict(db)
    return _parse_bool_setting(
        d.get(KEY_KB_SAG_EVENT_EXTRACT_ENABLED, DEFAULTS[KEY_KB_SAG_EVENT_EXTRACT_ENABLED])
    )


def get_kb_sag_event_extract_mode(db: Session) -> str:
    d = get_public_settings_dict(db)
    return _parse_kb_sag_event_extract_mode(
        d.get(KEY_KB_SAG_EVENT_EXTRACT_MODE, DEFAULTS[KEY_KB_SAG_EVENT_EXTRACT_MODE])
    )


def get_kb_sag_event_prompt_version(db: Session) -> int:
    d = get_public_settings_dict(db)
    return _parse_kb_sag_event_prompt_version(
        d.get(KEY_KB_SAG_EVENT_PROMPT_VERSION, DEFAULTS[KEY_KB_SAG_EVENT_PROMPT_VERSION])
    )


def is_kb_sag_event_embed_enabled(db: Session) -> bool:
    d = get_public_settings_dict(db)
    return _parse_bool_setting(
        d.get(KEY_KB_SAG_EVENT_EMBED_ENABLED, DEFAULTS[KEY_KB_SAG_EVENT_EMBED_ENABLED])
    )


def is_kb_sag_query_llm_enabled(db: Session) -> bool:
    d = get_public_settings_dict(db)
    return _parse_bool_setting(
        d.get(KEY_KB_SAG_QUERY_LLM_ENABLED, DEFAULTS[KEY_KB_SAG_QUERY_LLM_ENABLED])
    )


def get_kb_sag_event_fingerprint_fields(db: Session) -> dict[str, bool | str | int]:
    return {
        "sag_extract_enabled": is_kb_sag_event_extract_enabled(db),
        "sag_extract_mode": get_kb_sag_event_extract_mode(db),
        "sag_prompt_version": get_kb_sag_event_prompt_version(db),
        "sag_embed_enabled": is_kb_sag_event_embed_enabled(db),
    }


def get_kb_wiki_compile_min_sources(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> int:
    d = _settings_dict(db, user_id=user_id, effective=effective)
    return _parse_kb_wiki_compile_min_sources(
        d.get(KEY_KB_WIKI_COMPILE_MIN_SOURCES, DEFAULTS[KEY_KB_WIKI_COMPILE_MIN_SOURCES])
    )


def get_agent_run_retention_days(db: Session) -> int:
    d = get_public_settings_dict(db)
    return _parse_agent_run_retention_days(
        d.get(KEY_AGENT_RUN_RETENTION_DAYS, DEFAULTS[KEY_AGENT_RUN_RETENTION_DAYS])
    )


def get_kb_index_max_attempts(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> int:
    if user_id is not None or effective is not None:
        d = _settings_dict(db, user_id=user_id, effective=effective)
        return _parse_kb_index_max_attempts(d.get(KEY_KB_INDEX_MAX_ATTEMPTS, DEFAULTS[KEY_KB_INDEX_MAX_ATTEMPTS]))
    global _kb_index_max_attempts_cache
    import time

    now = time.time()
    with _cache_lock:
        if _kb_index_max_attempts_cache is not None:
            ts, val = _kb_index_max_attempts_cache
            if now - ts < _kb_index_max_attempts_cache_ttl_sec:
                return val
    d = get_public_settings_dict(db)
    val = _parse_kb_index_max_attempts(d.get(KEY_KB_INDEX_MAX_ATTEMPTS, DEFAULTS[KEY_KB_INDEX_MAX_ATTEMPTS]))
    with _cache_lock:
        _kb_index_max_attempts_cache = (now, val)
    return val


def is_kb_post_async_enabled(db: Session) -> bool:
    d = get_public_settings_dict(db)
    return _parse_bool_setting(d.get(KEY_KB_POST_ASYNC_ENABLED, DEFAULTS[KEY_KB_POST_ASYNC_ENABLED]))


def get_kb_post_max_attempts(
    db: Session,
    *,
    user_id: int | None = None,
    effective: dict[str, str] | None = None,
) -> int:
    if user_id is not None or effective is not None:
        d = _settings_dict(db, user_id=user_id, effective=effective)
        return _parse_kb_post_max_attempts(d.get(KEY_KB_POST_MAX_ATTEMPTS, DEFAULTS[KEY_KB_POST_MAX_ATTEMPTS]))
    d = get_public_settings_dict(db)
    return _parse_kb_post_max_attempts(d.get(KEY_KB_POST_MAX_ATTEMPTS, DEFAULTS[KEY_KB_POST_MAX_ATTEMPTS]))
