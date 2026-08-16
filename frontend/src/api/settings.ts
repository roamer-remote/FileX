import api from './index'

export interface ClipboardSettings {
  clipboard_prefix: string
  clipboard_suffix: string
  /** 标签关系图：单文件节点基准直径（px）；直径 = 文件数 × 显示比例 × 本项 */
  tag_graph_single_node_symbol_size: number
  tag_graph_node_display_ratio: number
  /** 标签关系图中节点连线的默认线宽（px） */
  tag_graph_edge_line_width: number
  /** 是否在资料库顶栏展示「标签关系」Tab */
  tag_graph_enabled?: boolean
  /** 单文件上传大小上限（MB），与系统参数一致 */
  max_upload_size_mb: number
  /** 是否启用共享知识空间（侧栏空间切换、管理端空间运维等） */
  shared_workspaces_enabled?: boolean
  /** 全局正文提取引擎（legacy / liteparse / docling / mineru / insavlo） */
  kb_extract_provider?: string
  /** Insavlo 运行配置完整时普通用户侧才展示该 provider */
  kb_extract_insavlo_ready?: boolean
  /** 智能检索 Drawer「条数」缺省值（5–50） */
  kb_search_default_top_k?: number
  /** 资料库 MQ 处理完成/失败时浏览器 TTS 语音提示 */
  kb_voice_notify_enabled?: boolean
  /** 资料库语音播报等待过期时间（秒）：超过该秒数后丢弃所有等待/挂起语音。1–3600，默认 120 */
  kb_voice_notify_playback_ttl_seconds?: number
  /** SAG 事件抽取是否已在系统侧启用（门控语义搜索多跳开关） */
  kb_sag_event_extract_enabled?: boolean
  /** 知识库后处理 LLM provider（ollama / openai_compatible） */
  kb_post_llm_provider?: string
  /** OpenAI-compatible 后处理 LLM Base URL */
  kb_post_llm_base_url?: string
  /** 后处理 LLM API Key 永不回显；仅用于类型兼容 */
  kb_post_llm_api_key?: string
  /** 是否已保存后处理 LLM API Key */
  kb_post_llm_has_api_key?: boolean
  /** OpenAI-compatible 后处理 LLM 模型名 */
  kb_post_llm_model?: string
  /** OpenAI-compatible 后处理 LLM 请求超时 */
  kb_post_llm_timeout_sec?: number
  /** OpenAI-compatible JSON 输出模式 */
  kb_post_llm_json_mode?: string
}

export function getClipboardSettings() {
  return api.get<ClipboardSettings>('/settings/clipboard')
}


export type UserPreferencesEffective = {
  tag_graph_enabled: boolean
  tag_graph_single_node_symbol_size: number
  tag_graph_node_display_ratio: number
  tag_graph_edge_line_width: number
  kb_extract_provider: string
  kb_chunk_profile: string
  kb_index_max_attempts: number
  kb_voice_notify_enabled: boolean
  kb_voice_notify_playback_ttl_seconds: number
  kb_search_hybrid_enabled: boolean
  kb_fts_config: string
  kb_search_min_score: number
  kb_search_boost_keyword_bonus: number
  kb_search_mmr_lambda: number
  kb_search_filename_boost: number
  kb_search_modality_boost_enabled: boolean
  kb_search_modality_boost: number
  kb_search_default_top_k: number
  kb_wiki_compile_min_sources: number
}

export type UserPreferencesResponse = {
  effective: UserPreferencesEffective
  overrides: Record<string, string>
  inherited_keys: string[]
}

export type UserPreferencesUpdate = Partial<UserPreferencesEffective>

export function getUserPreferences(config?: { skipErrorToast?: boolean }) {
  return api.get<UserPreferencesResponse>('/settings/user-preferences', config as never)
}

export function putUserPreferences(body: UserPreferencesUpdate) {
  return api.put<UserPreferencesResponse>('/settings/user-preferences', body)
}

export function resetUserPreferences(keys?: string[]) {
  return api.post<UserPreferencesResponse>(
    '/settings/user-preferences/reset',
    keys ? { keys } : {},
  )
}
