import api from './index'
import type { FileListResponse } from './files'
import type { MqUserActiveTask } from './mq'

export interface AdminCreateUserBody {
  username: string
  password: string
  is_admin: boolean
}

export interface SystemSettingsPayload {
  clipboard_prefix: string
  clipboard_suffix: string
  tag_graph_single_node_symbol_size: number
  tag_graph_node_display_ratio: number
  tag_graph_edge_line_width: number
  tag_graph_enabled: boolean
  max_upload_size_mb: number
  workspace_backup_max_mb: number
  agent_run_retention_days: number
  kb_index_max_attempts: number
  kb_post_async_enabled?: boolean
  kb_post_max_attempts?: number
  shared_workspaces_enabled: boolean
  enterprise_rbac_enabled?: boolean
  kb_search_hybrid_enabled: boolean
  kb_chunk_profile: string
  kb_chunk_size?: number | null
  kb_chunk_overlap?: number | null
  kb_chunk_split_recursive?: boolean
  kb_embed_cache_enabled?: boolean
  kb_embed_effective_max_chars?: number
  // T-4: 大文档（PDF 等）索引优化阈值
  kb_large_doc_char_threshold?: number
  kb_large_doc_chunk_size?: number
  kb_large_doc_chunk_overlap?: number
  kb_large_doc_post_enabled?: boolean
  kb_large_doc_raptor_enabled?: boolean
  kb_raptor_enabled?: boolean
  kb_raptor_min_chars?: number
  kb_extract_provider: string
  kb_pdf_inspector_enabled: boolean
  kb_search_min_score: number
  kb_search_boost_keyword_bonus: number
  kb_search_mmr_lambda: number
  kb_search_filename_boost: number
  kb_search_modality_boost: number
  kb_search_modality_boost_enabled: boolean
  kb_search_default_top_k: number
  kb_fts_config: string
  kb_wiki_lint_interval_hours?: number
  kb_wiki_compile_min_sources: number
  kb_voice_notify_enabled: boolean
  kb_voice_notify_playback_ttl_seconds: number
  kb_extract_insavlo_enabled: boolean
  kb_extract_insavlo_base_url: string
  kb_extract_insavlo_api_key?: string
  kb_extract_insavlo_webhook_secret?: string
  kb_extract_insavlo_skill_code: string
  kb_extract_insavlo_callback_origin: string
  kb_extract_insavlo_timeout_minutes: number
  kb_extract_insavlo_has_api_key: boolean
  kb_extract_insavlo_has_webhook_secret: boolean
  kb_extract_insavlo_ready: boolean
  kb_ingestion_pipeline_json: string
  builtin_routes?: Array<{
    match: { ext?: string[]; mime_prefix?: string }
    extract_provider: string
    engine?: string
    builtin?: boolean
    readonly?: boolean
  }>
  ollama_base_url: string
  ollama_embed_model: string
  ollama_embed_dim: number
  ollama_chat_model: string
  ollama_api_key?: string
  ollama_has_api_key?: boolean
  ollama_timeout_sec: number
  ollama_embed_batch_size: number
  ollama_num_parallel?: number
  ollama_embed_concurrency?: number
  kb_post_llm_provider?: string
  kb_post_llm_base_url?: string
  kb_post_llm_api_key?: string
  kb_post_llm_has_api_key?: boolean
  kb_post_llm_model?: string
  kb_post_llm_timeout_sec?: number
  kb_post_llm_json_mode?: string
  clear_kb_post_llm_api_key?: boolean
  clear_ollama_api_key?: boolean
  kb_ragas_online_eval_enabled?: boolean
  kb_ragas_online_eval_sample_rate?: number
  kb_ragas_online_eval_timeout_seconds?: number
  kb_ragas_llm_provider?: string
  kb_ragas_llm_base_url?: string
  kb_ragas_llm_api_key?: string
  kb_ragas_llm_has_api_key?: boolean
  kb_ragas_llm_model?: string
  kb_ragas_llm_timeout_seconds?: number
  kb_ragas_eval_concurrency?: number
  kb_ragas_eval_context_max_count?: number
  kb_ragas_eval_context_max_chars_per_item?: number
  kb_ragas_eval_context_max_total_chars?: number
  clear_kb_ragas_llm_api_key?: boolean
  mineru_min_batch_mode?: string
  mineru_min_batch_inference_size?: number
  mineru_min_batch_floor?: number
  mineru_parse_method?: string
  mineru_formula_enable?: boolean
  mineru_table_enable?: boolean
  mineru_parse_timeout_sec?: number
  mineru_rpc_timeout_sec?: number
  mineru_page_chunk_enabled?: boolean
  mineru_page_chunk_threshold?: number
  mineru_page_chunk_pages?: number
  mineru_table_auto_rotate?: boolean
  mineru_table_rotate_max_tables?: number
  mineru_table_rotate_timeout_sec?: number
  agent_skill_install_prompt?: string
  warnings?: string[]
  kb_sag_event_extract_enabled: boolean
  kb_sag_event_extract_mode: string
  kb_sag_event_prompt_version: number
  kb_sag_event_embed_enabled: boolean
  kb_sag_query_llm_enabled: boolean
  kb_multi_repr_enabled: boolean  // 154: 146 P2 multi-repr master switch
  clear_insavlo_api_key?: boolean
  clear_insavlo_webhook_secret?: boolean
}


export interface MqActiveTask extends MqUserActiveTask {
  username: string
}

export interface MqQueueStatus {
  name: string
  label: string
  online: boolean
  message_count: number
  consumer_count: number
  /** 主队列：kb-indexer 正在执行索引任务 */
  consumer_busy?: boolean
  /** 主队列：库中 queued 任务数（可能尚未投递到 RabbitMQ） */
  jobs_pending?: number
  /** 主队列：queued + 正在索引，侧栏「待处理与执行中」 */
  backlog_total?: number
}

export interface MqSystemResources {
  cpu_percent?: number | null
  gpu: {
    available: boolean
    gpu_usable?: boolean
    capability?: 'high' | 'medium' | 'low' | 'cpu_only'
    reason_code?: 'cpu_only_no_cuda' | 'cpu_only_probe_failed' | 'cpu_only_insufficient_memory' | null
    degradation_reason?: 'high_warmup_required' | null
    gpu_index?: number | null
    compute_capability?: string | null
    processes?: Array<{ pid: number; name: string; memory_used_mb: number }>
    process_probe_status?: 'ok' | 'failed' | 'not_run'
    name?: string | null
    util_percent?: number | null
    memory_used_mb?: number | null
    memory_total_mb?: number | null
    memory_free_mb?: number | null
  }
  /** gpu-scheduler worker 持久化的观测状态（164 §9） */
  gpu_scheduler?: {
    model_group?: 'none' | 'raptor' | 'mineru' | 'switching' | null
    model_status?: string | null
    switch_started_at?: string | null
    switch_finished_at?: string | null
    last_switch_duration_ms?: number | null
    last_failure_kind?: string | null
    last_failure_reason?: string | null
    last_failure_at?: string | null
    updated_at?: string | null
  } | null
  /** 处于 waiting_gpu 的 extract/post 任务汇总（164 §9） */
  gpu_waiting?: {
    count: number
    oldest_wait_seconds?: number | null
    reason_codes?: string[]
  } | null
}

export interface MqStatusPayload {
  connected: boolean
  broker_display: string
  error?: string | null
  updated_at: string
  queues: MqQueueStatus[]
  active_tasks?: MqUserActiveTask[]
  system_resources?: MqSystemResources | null
}

export function getAdminMqStatus() {
  return api.get<MqStatusPayload>('/admin/mq-status', { skipErrorToast: true })
}

export interface MqQueueMessageItem {
  index: number
  job_id: number | null
  last_error: string | null
  body_preview: string
  raw_body: string
  redelivered: boolean
  duplicate_count?: number
}

export interface MqQueueMessagesPayload {
  queue_name: string
  /** RabbitMQ 队列当前深度 */
  message_count: number
  /** 本次预览条数，与 items 一致 */
  peek_count?: number
  raw_peek_count?: number
  items: MqQueueMessageItem[]
  truncated: boolean
}

export interface MqQueuedJobItem {
  job_id: number
  file_id: number
  filename: string
  username: string
  updated_at?: string | null
}

export interface MqQueuedJobsPayload {
  total: number
  items: MqQueuedJobItem[]
  truncated: boolean
}

export function getAdminMqQueuedJobs(limit = 50) {
  return api.get<MqQueuedJobsPayload>('/admin/mq/queued-jobs', { params: { limit } })
}

export function getAdminMqExtractQueuedJobs(limit = 50) {
  return api.get<MqQueuedJobsPayload>('/admin/mq/extract-queued-jobs', { params: { limit } })
}

export function getAdminMqPostQueuedJobs(limit = 50) {
  return api.get<MqQueuedJobsPayload>('/admin/mq/post-queued-jobs', { params: { limit } })
}

export function getAdminMqQueueMessages(queueName: string, limit = 50) {
  return api.get<MqQueueMessagesPayload>(
    `/admin/mq/queues/${encodeURIComponent(queueName)}/messages`,
    { params: { limit } },
  )
}

export function dedupeAdminMqQueueMessages(queueName: string) {
  return api.post<{ queue_name: string; removed: number; message_count: number }>(
    `/admin/mq/queues/${encodeURIComponent(queueName)}/messages/dedupe`,
  )
}

export function deleteAdminMqQueueMessages(
  queueName: string,
  body: { purge?: boolean; job_id?: number; index?: number },
) {
  return api.post<{ queue_name: string; removed: number; message_count: number }>(
    `/admin/mq/queues/${encodeURIComponent(queueName)}/messages/delete`,
    body,
  )
}

export function getAdminSystemSettings() {
  return api.get<SystemSettingsPayload>('/admin/system-settings')
}

export function putAdminSystemSettings(body: Partial<SystemSettingsPayload>) {
  return api.put<SystemSettingsPayload>('/admin/system-settings', body)
}

export interface TestInsavloSettingsResponse {
  ok: boolean
  ready: boolean
  errors: string[]
  message: string
}

export function testAdminInsavloSettings() {
  return api.post<TestInsavloSettingsResponse>('/admin/system-settings/test-insavlo')
}

export interface TestOllamaSettingsResponse {
  ok: boolean
  base_url: string
  embed_model: string
  tags_status?: number | null
  model_present: boolean
  models: string[]
  errors: string[]
  compose_network_hint?: string | null
  message: string
}

export function testAdminOllamaSettings() {
  return api.post<TestOllamaSettingsResponse>('/admin/system-settings/test-ollama')
}

export interface MineruVersionResponse {
  mineru_version?: string | null
  sidecar_version?: string | null
  error?: string
}

export function getAdminMineruVersion() {
  return api.get<MineruVersionResponse>('/admin/mineru-version')
}


export interface AdminUserRow {
  id: number
  username: string
  is_admin: boolean
  is_active: boolean
  created_at: string
  last_login_at: string
  wechat_nickname: string
  wechat_openid: string
}

export interface AdminUserListSummary {
  admin_count: number
  active_today_count: number
}

export interface AdminUserListResponse {
  items: AdminUserRow[]
  total: number
  page: number
  page_size: number
  summary: AdminUserListSummary
}

export function listAdminUsers(params?: { page?: number; page_size?: number }) {
  return api.get<AdminUserListResponse>('/admin/users', {
    params: {
      page: params?.page ?? 1,
      page_size: params?.page_size ?? 20,
    },
  })
}

export interface AdminLogItem {
  id: number
  user_id: number
  username: string
  action: string
  target_type: string | null
  target_id: number | null
  detail: string | null
  created_at: string
}

export interface AdminLogListResponse {
  items: AdminLogItem[]
  total: number
  page: number
  page_size: number
}

export interface AdminLogDeleteResponse {
  deleted: number
}

export function listAdminLogs(params?: { page?: number; page_size?: number; user_id?: number }) {
  return api.get<AdminLogListResponse>('/admin/logs', {
    params: {
      page: params?.page ?? 1,
      page_size: params?.page_size ?? 20,
      ...(typeof params?.user_id === 'number' && !Number.isNaN(params.user_id)
        ? { user_id: params.user_id }
        : {}),
    },
  })
}

export function deleteAdminLog(logId: number) {
  return api.delete<AdminLogDeleteResponse>(`/admin/logs/${logId}`)
}

export function deleteAdminLogsBatch(ids: number[]) {
  return api.post<AdminLogDeleteResponse>('/admin/logs/delete', { ids })
}

export function purgeAdminLogs(userId?: number) {
  return api.post<AdminLogDeleteResponse>('/admin/logs/purge', null, {
    params: typeof userId === 'number' && !Number.isNaN(userId) ? { user_id: userId } : undefined,
  })
}

export function createAdminUser(body: AdminCreateUserBody) {
  return api.post<{
    id: number
    username: string
    is_admin: boolean
    is_active: boolean
    created_at: string
  }>('/admin/users', body, { skipErrorToast: true })
}

/** 通过 PUT /admin/users/:id 写入 new_password，与同路由下的启用/权限更新一致，避免部分环境下 POST 子路径返回 405 */
export function resetAdminUserPassword(userId: number, newPassword: string) {
  return api.put<{ message: string }>(
    `/admin/users/${userId}`,
    { new_password: newPassword },
    { skipErrorToast: true },
  )
}

export function getAdminFiles(params: {
  folder_id?: number | null
  user_id?: number | null
  search?: string
  sort_time?: 'desc' | 'asc'
  page?: number
  page_size?: number
}) {
  const q: Record<string, string | number> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  }
  if (params.search) q.search = params.search
  if (params.folder_id != null) q.folder_id = Number(params.folder_id)
  if (typeof params.user_id === 'number' && !Number.isNaN(params.user_id)) q.user_id = params.user_id
  if (params.sort_time) q.sort_time = params.sort_time
  return api.get<FileListResponse>('/admin/files', { params: q })
}


export interface AdminKbReindexAllResponse {
  candidate_count: number
  enqueued_count: number
  message: string
}

export function postAdminKbReindexAll(body?: { user_id?: number; force?: boolean }) {
  return api.post<AdminKbReindexAllResponse>('/admin/kb/reindex-all', body ?? { force: true })
}

export interface AdminWikiRebuildResult {
  rebuilt_count: number
  file_count: number
  message?: string
}

export function adminWikiLint(body?: { user_id?: number }) {
  return api.post('/admin/kb/wiki-lint', body ?? {})
}

export function adminRebuildWikiLinks(body?: { user_id?: number; batch_size?: number }) {
  return api.post<AdminWikiRebuildResult>('/admin/kb/rebuild-wiki-links', body ?? {})
}

export interface PipelineTopologyNode {
  id: string
  label: string
  kind: string
  description?: string | null
  highlight: boolean
}

export interface PipelineTopologyEdge {
  source: string
  target: string
}

export interface EffectivePipelineRoute {
  route_index: number
  match_label: string
  extract_provider: string
}

export interface PipelineTopologyResponse {
  nodes: PipelineTopologyNode[]
  edges: PipelineTopologyEdge[]
  effective_routes: EffectivePipelineRoute[]
  global_default_provider: string
  stages: Record<string, boolean>
}

export function getKbPipelineTopology() {
  return api.get<PipelineTopologyResponse>('/admin/kb-pipeline/topology')
}

export type PipelineMetricsWindow = '1h' | '24h' | '7d'

export interface PipelineQueueMetric {
  name: string
  label: string
  message_count: number
  warning: boolean
  deep_link: string
}

export interface PipelineKpiMetric {
  key: string
  value: number
  warning: boolean
  deep_link?: string | null
}

export interface ProviderFailureStat {
  provider: string
  failure_count: number
  success_count: number
  failure_rate: number
}

export interface PipelineStageAvgMs {
  extract_provider_ms?: number | null
  extract_persist_ms?: number | null
  index_embed_ms?: number | null
  index_persist_ms?: number | null
  index_post_ms?: number | null
}

export interface PipelineRecentEvent {
  id: number
  action: string
  user_id: number
  username: string
  target_id?: number | null
  detail?: string | null
  created_at: string
  log_deep_link: string
}

export interface PipelineMetricsResponse {
  window: PipelineMetricsWindow
  generated_at: string
  cached: boolean
  queues: PipelineQueueMetric[]
  kpis: PipelineKpiMetric[]
  provider_failures: ProviderFailureStat[]
  avg_stage_ms: PipelineStageAvgMs
  recent_events: PipelineRecentEvent[]
  warnings: string[]
}

export function getKbPipelineMetrics(window: PipelineMetricsWindow = '24h') {
  return api.get<PipelineMetricsResponse>('/admin/kb-pipeline/metrics', {
    params: { window },
  })
}

export type KbSearchEvalStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped'

export interface KbSearchEvalSummary {
  days: number
  total_count: number
  succeeded_count: number
  failed_count: number
  skipped_count: number
  pending_count: number
  running_count: number
  failure_rate: number
  avg_faithfulness: number | null
  avg_context_precision: number | null
  enabled: boolean
  sample_rate: number
  timeout_seconds: number
}

export interface KbSearchEvalTrendPoint {
  bucket: string
  avg_faithfulness: number | null
  avg_context_precision: number | null
  sample_count: number
  failure_rate: number
  pending_count: number
  running_count: number
  failed_count: number
  skipped_count: number
  failure_stage_counts: Record<string, number>
}

export interface KbSearchEvalTrendResponse {
  days: number
  granularity: 'hour' | 'day'
  points: KbSearchEvalTrendPoint[]
}

export interface KbSearchEvalSample {
  id: number
  user_id: number
  workspace_id: number | null
  agent_run_id: string | null
  search_trace_id: string | null
  query_hash: string
  query_preview: string
  answer_hash: string
  answer_preview: string
  context_count: number
  context_file_ids: number[]
  context_chunk_ids: number[]
  faithfulness_score: number | null
  context_precision_score: number | null
  metric_provider: string
  metric_version: string
  metric_variant: string
  llm_provider: string | null
  llm_model: string | null
  status: KbSearchEvalStatus
  error_code: string | null
  error_message: string | null
  duration_ms: number | null
  queue_duration_ms: number | null
  faithfulness_duration_ms: number | null
  context_precision_duration_ms: number | null
  failure_stage: string | null
  context_budget_version: string | null
  source_context_count: number | null
  selected_context_count: number | null
  selected_context_chars: number | null
  created_at: string | null
  evaluated_at: string | null
}

export interface KbSearchEvalSamplesResponse {
  items: KbSearchEvalSample[]
  total: number
}

export interface KbSearchEvalQueryParams {
  days?: number
  status_filter?: KbSearchEvalStatus
  low_score_threshold?: number | null
  limit?: number
  workspace_id?: number | null
  user_id?: number | null
}

export function getAdminKbSearchEvalSummary(params?: KbSearchEvalQueryParams) {
  return api.get<KbSearchEvalSummary>('/admin/kb-search-eval/summary', { params })
}

export function getAdminKbSearchEvalTrend(params?: KbSearchEvalQueryParams & { granularity?: 'hour' | 'day' }) {
  return api.get<KbSearchEvalTrendResponse>('/admin/kb-search-eval/trend', { params })
}

export function getAdminKbSearchEvalSamples(params?: KbSearchEvalQueryParams) {
  return api.get<KbSearchEvalSamplesResponse>('/admin/kb-search-eval/samples', { params })
}
