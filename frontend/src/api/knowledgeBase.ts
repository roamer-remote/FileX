import api from './index'
import type { ExtractProvider } from '@/utils/extractProviders'
import { kbSearchQueryParams } from '@/lib/kbSearchQueryParams'


import { FOLDER_ID_UNCATEGORIZED, type FolderSelection } from '@/lib/folderTree'
import {
  kbWorkspaceQueryParams,
  libraryReportQueryParams,
  resolveActiveWorkspaceId,
} from '@/lib/kbWorkspaceParams'

export interface WikiLinkGraphNode {
  id: number
  name: string
  value: number
  page_kind: string
  wiki_slug: string | null
}

export interface WikiLinkGraphEdge {
  source: number
  target: number
  value: number
  edge_type: 'file_direct' | 'wiki_topic' | 'wiki_coref'
  wiki_slug?: string | null
}

export interface WikiLinkGraphResponse {
  nodes: WikiLinkGraphNode[]
  links: WikiLinkGraphEdge[]
  truncated: boolean
  total_files_with_links: number
}

function wikiLinkGraphFolderParams(folderFilter: FolderSelection): { folder_id?: number } {
  if (folderFilter === 'all') return {}
  if (folderFilter === 'uncategorized') return { folder_id: FOLDER_ID_UNCATEGORIZED }
  return { folder_id: folderFilter }
}

export async function getWikiLinkGraph(
  folderFilter: FolderSelection = 'all',
): Promise<WikiLinkGraphResponse> {
  const res = await api.get<WikiLinkGraphResponse>('/knowledge-base/link-graph', {
    params: { ...kbWorkspaceQueryParams(), ...wikiLinkGraphFolderParams(folderFilter) },
  })
  return res.data
}


export interface WikiCandidateItem {
  wiki_slug: string
  source_count: number
  sample_file_ids: number[]
}

export interface WikiLintResponse {
  broken_links: Record<string, unknown>[]
  acl_broken_links: Record<string, unknown>[]
  orphan_pages: Record<string, unknown>[]
  missing_slug: Record<string, unknown>[]
  stale_wiki_index: boolean
  pending_concepts?: WikiCandidateItem[]
}

export async function postWikiLint(): Promise<WikiLintResponse> {
  const res = await api.post<WikiLintResponse>('/knowledge-base/lint', null, {
    params: kbWorkspaceQueryParams(),
  })
  return res.data
}

export interface KbLogEntryItem {
  id: number
  entry: string
  workspace_id: number | null
  created_at: string
}

export interface KbLogListResponse {
  items: KbLogEntryItem[]
  total: number
  limit: number
  offset: number
}

export async function getKbLog(params?: { limit?: number; offset?: number }): Promise<KbLogListResponse> {
  const res = await api.get<KbLogListResponse>('/knowledge-base/log', {
    params: { ...kbWorkspaceQueryParams(), ...params },
  })
  return res.data
}

export async function appendKbLog(
  entry: string,
  workspaceId?: number | null,
): Promise<{ id: number; message: string }> {
  const body: { entry: string; workspace_id?: number } = { entry }
  if (workspaceId != null) body.workspace_id = workspaceId
  const res = await api.post<{ id: number; message: string }>('/knowledge-base/log', body)
  return res.data
}

export interface WikiPageListItem {
  file_id: number
  title: string
  wiki_slug: string
  page_kind: string
  has_md: boolean
  linked_source_count: number
  workspace_id: number | null
}


export async function getWikiCandidates(minSources?: number): Promise<WikiCandidateItem[]> {
  const params: Record<string, number> = { ...kbWorkspaceQueryParams() }
  if (minSources != null) params.min_sources = minSources
  const res = await api.get<{ items: WikiCandidateItem[] }>("/knowledge-base/wiki/candidates", { params })
  return res.data.items
}

export async function getWikiPageBySlug(slug: string): Promise<WikiPageListItem | null> {
  try {
    const res = await api.get<WikiPageListItem>(`/knowledge-base/wiki/pages/by-slug/${encodeURIComponent(slug)}`, {
      params: kbWorkspaceQueryParams(),
      skipErrorToast: true,
    })
    return res.data
  } catch (e: unknown) {
    const err = e as { response?: { status?: number } }
    if (err.response?.status === 404) return null
    throw e
  }
}

export interface WikiPageCreatePayload {
  title: string
  wiki_slug: string
  page_kind: "entity" | "concept" | "synthesis"
  markdown?: string
  workspace_id?: number
}

export async function createWikiPage(body: WikiPageCreatePayload): Promise<{ message: string }> {
  const payload = { ...body, workspace_id: body.workspace_id ?? resolveActiveWorkspaceId() ?? undefined }
  const res = await api.post<{ message: string }>("/knowledge-base/wiki/pages", payload)
  return res.data
}

export async function patchWikiPageSlug(
  fileId: number,
  wikiSlug: string,
): Promise<{ message: string; wiki_slug: string; notes_updated: number }> {
  const res = await api.patch<{ message: string; wiki_slug: string; notes_updated: number }>(
    `/knowledge-base/wiki/pages/${fileId}`,
    { wiki_slug: wikiSlug },
    { params: kbWorkspaceQueryParams() },
  )
  return res.data
}

export interface WikiPageListResult {
  items: WikiPageListItem[]
  total: number
  page: number
  page_size: number
}

export async function getWikiPages(params?: { page?: number; page_size?: number }): Promise<WikiPageListResult> {
  const res = await api.get<WikiPageListResult>('/knowledge-base/wiki/pages', {
    params: {
      ...kbWorkspaceQueryParams(),
      page: params?.page ?? 1,
      page_size: params?.page_size ?? 100,
    },
  })
  return res.data
}

export interface WikiLinkedSourceItem {
  file_id: number
  source_name: string
}

export async function getWikiPageLinkedSources(wikiSlug: string): Promise<WikiLinkedSourceItem[]> {
  const res = await api.get<{ items: WikiLinkedSourceItem[] }>('/knowledge-base/wiki/pages/linked-sources', {
    params: { ...kbWorkspaceQueryParams(), wiki_slug: wikiSlug },
  })
  return res.data.items
}

export interface KnowledgeBaseRebuildResult {
  message: string
  content: string
  file_count: number
  recovered_from_corrupt?: boolean
  backup_name?: string | null
}

/** POST /knowledge-base/rebuild — 从数据库重建 kb_index.md AUTO 表 */
export async function rebuildKnowledgeBaseIndex(): Promise<KnowledgeBaseRebuildResult> {
  const res = await api.post<KnowledgeBaseRebuildResult>('/knowledge-base/rebuild')
  return res.data
}

export async function getKnowledgeBaseIndex(): Promise<string | null> {
  try {
    const res = await api.get<string>('/knowledge-base/', {
      responseType: 'text',
      transformResponse: [(d) => d],
      skipErrorToast: true,
    })
    return typeof res.data === 'string' ? res.data : null
  } catch (e: unknown) {
    const err = e as { response?: { status?: number } }
    if (err.response?.status === 404) return null
    throw e
  }
}


export interface KbChunkSnippet {
  chunk_index: number | null
  text: string
  score: number
  heading_path?: string | null
  citation_label?: string | null
}

export type KbChunkLocType = 'pdf_page' | 'slide' | 'sheet'

export interface KbChunkLocation {
  type: KbChunkLocType
  page?: number
  slide?: number
  sheet_index?: number
  sheet_name?: string | null
}

export interface KbSearchDebugFunnel {
  vector_candidates: number
  fts_candidates: number
  merged_unique: number
  after_acl_filter: number
  after_min_score: number
  after_rerank: number
  after_mmr: number
  filename_boost_applied: number
}

export interface KbSearchMeta {
  hybrid_enabled: boolean
  rerank_enabled: boolean
  rerank_applied: boolean
  min_score?: number | null
  mmr_lambda?: number | null
  boost_keyword_bonus?: number | null
  filename_boost_enabled?: boolean | null
  filename_boost_value?: number | null
  modality_boost_enabled?: boolean | null
  modality_boost_value?: number | null
  modality_intent?: string[] | null
  effective_hybrid?: boolean | null
  query_expansion_enabled?: boolean | null
  expanded_terms?: string[] | null
  effective_fts_config?: string | null
  debug?: boolean
  cache_hit?: boolean | null
  cache_similarity?: number | null
  cache_entry_id?: number | null
  evidence_mode?: 'chunk' | 'monte_carlo' | null
  monte_carlo_sample_count?: number | null
  raptor_expanded?: boolean | null
  raptor_drilldown_ids?: number[] | null
  raptor_added_hits?: number | null
  debug_funnel?: KbSearchDebugFunnel | null
  sag_expanded?: boolean | null
  sag_added_hits?: number | null
  sag_neighbor_event_ids?: number[] | null
  sag_mode_requested?: 'fast' | 'standard' | null
  sag_mode_effective?: 'fast' | 'standard' | null
  sag_mode_degraded?: boolean | null
  search_trace?: Record<string, unknown> | null
  processing_hit_count?: number
  processing_file_ids?: number[]
}

export interface KbChunkHit {
  chunk_id?: number | null
  file_id: number
  original_name: string
  has_md: boolean
  chunk_index: number | null
  source: string | null
  text: string
  score: number
  char_start: number | null
  char_end: number | null
  matched_chunks?: number
  file_chunk_count?: number | null
  heading_path?: string | null
  block_type?: string | null
  context_text?: string | null
  vector_score?: number
  rerank_score?: number
  boost_keywords?: string | null
  keyword_boost?: number | null
  filename_boost?: number | null
  modality_boost?: number | null
  content_kind?: string | null
  base_score?: number | null
  citation?: string | Record<string, unknown>
  citation_label?: string | null
  citation_tier?: 'paginated' | 'document_only'
  location?: KbChunkLocation | null
  snippets?: KbChunkSnippet[] | null
  source_kind?: string | null
  is_final?: boolean
  content_confidence?: 'none' | 'partial' | 'final'
  processing_stage?: string | null
  processing_message?: string | null
  expected_next_stage?: string | null
}

export interface KbSearchResponse {
  items: KbChunkHit[]
  embedding_model: string
  top_k: number
  /** ISO 8601 UTC（Z）；本响应检索快照时刻 */
  fetched_at: string
  /** 智能体提示：资料库可能已变更，须每轮重新检索 */
  agent_notice?: string
  meta?: KbSearchMeta | null
}

export interface KbSearchParams {
  query: string
  top_k?: number
  file_ids?: number[]
  tags?: string[]
  tag_mode?: 'or' | 'and'
  include_not_ready?: boolean
  group_by_file?: boolean
  context_chunks?: number
  cross_workspace?: boolean
  debug?: boolean
  filename_boost?: boolean
  modality_boost?: boolean
  hybrid?: boolean | null
  query_expansion?: boolean
  use_query_cache?: boolean
  evidence_mode?: 'chunk' | 'monte_carlo'
  evidence_sample_k?: number
  raptor_expand?: boolean
  raptor_drill_k?: number
  expand_sag_events?: boolean
  sag_search_mode?: 'fast' | 'standard'
  return_search_trace?: boolean
  citation_format?: 'none' | 'markdown' | 'json'
  /** 仅检索普通资料（page_kind=source），排除 Wiki 主题页 */
  source_files_only?: boolean
}

export async function searchKnowledgeBase(params: KbSearchParams): Promise<KbSearchResponse> {
  const { cross_workspace, ...body } = params
  const res = await api.post<KbSearchResponse>('/knowledge-base/search', body, {
    params: kbSearchQueryParams(cross_workspace),
  })
  return res.data
}


export async function reextractKnowledgeBaseFile(
  fileId: number,
  options?: { force?: boolean; provider?: ExtractProvider },
): Promise<{ file_id: number; extract_status: string }> {
  const body: { force?: boolean; provider?: string } = {}
  if (options?.force) body.force = true
  if (options?.provider) body.provider = options.provider
  const res = await api.post<{ file_id: number; extract_status: string }>(
    `/knowledge-base/files/${fileId}/reextract`,
    body,
  )
  return res.data
}

export async function forceRaptorKnowledgeBaseFile(
  fileId: number,
): Promise<{ file_id: number; kb_post_status: string; job_id: number }> {
  const res = await api.post<{ file_id: number; kb_post_status: string; job_id: number }>(
    `/knowledge-base/files/${fileId}/force-raptor`,
    {},
  )
  return res.data
}

export async function reindexKnowledgeBaseFile(
  fileId: number,
  options?: { force?: boolean },
): Promise<{ file_id: number; index_status: string }> {
  const body: { force?: boolean } = {}
  if (options?.force) body.force = true
  const res = await api.post<{ file_id: number; index_status: string }>(
    `/knowledge-base/files/${fileId}/reindex`,
    body,
  )
  return res.data
}

export interface KbEmbeddingPreview {
  dim: number
  head: number[]
  norm: number
}

export interface KbChunkDetail {
  id: number
  chunk_index: number
  source: string
  text: string
  char_start: number
  char_end: number
  embedding_model: string
  embedding_dim: number
  embedding_preview: KbEmbeddingPreview
  created_at: string | null
  embedding?: number[]
  boost_keywords?: string | null
  keyword_boost?: number | null
  heading_path?: string | null
  block_type?: string | null
  content_kind?: string | null
  content_meta?: Record<string, unknown> | null
  loc_label?: string | null
}

export interface KbChunkListResponse {
  file_id: number
  original_name: string
  index_status: string
  chunk_count: number
  kb_index_manual_override?: boolean
  embedding_dim: number
  items: KbChunkDetail[]
  total: number
  page: number
  page_size: number
}

export interface ListKbChunksParams {
  page?: number
  page_size?: number
  include_embedding?: boolean
}

export async function listKnowledgeBaseFileChunks(
  fileId: number,
  params?: ListKbChunksParams,
): Promise<KbChunkListResponse> {
  const res = await api.get<KbChunkListResponse>(`/knowledge-base/files/${fileId}/chunks`, { params })
  return res.data
}

export interface KbChunkPatchParams {
  text?: string
  boost_keywords?: string
  reembed?: boolean
}

export interface KbChunkPatchResult {
  chunk_id: number
  file_id: number
  chunk_index: number
  text: string
  boost_keywords?: string | null
  keyword_boost?: number | null
  embedding_model: string
}

export async function patchKnowledgeBaseChunk(
  fileId: number,
  chunkId: number,
  body: KbChunkPatchParams,
): Promise<KbChunkPatchResult> {
  const res = await api.patch<KbChunkPatchResult>(
    "/knowledge-base/files/" + fileId + "/chunks/" + chunkId,
    body,
  )
  return res.data
}

export interface KbSagEntityItem {
  entity_name: string
  entity_type: string
}

export interface KbSagEventItem {
  id: number
  chunk_id: number
  chunk_index: number | null
  title: string
  summary: string
  content: string
  extract_layer: string
  entities: KbSagEntityItem[]
  created_at: string | null
}

export interface KbSagEventListResponse {
  file_id: number
  original_name: string
  items: KbSagEventItem[]
  total: number
  page: number
  page_size: number
}

export interface ListKbSagEventsParams {
  page?: number
  page_size?: number
}

export async function listKnowledgeBaseFileSagEvents(
  fileId: number,
  params?: ListKbSagEventsParams,
): Promise<KbSagEventListResponse> {
  const res = await api.get<KbSagEventListResponse>(`/knowledge-base/files/${fileId}/sag-events`, {
    params,
    skipErrorToast: true,
  })
  return res.data
}

export async function getKnowledgeBaseChunkSagEvent(
  fileId: number,
  chunkId: number,
): Promise<KbSagEventItem | null> {
  try {
    const res = await api.get<KbSagEventItem>(
      `/knowledge-base/files/${fileId}/chunks/${chunkId}/sag-event`,
      { skipErrorToast: true },
    )
    return res.data
  } catch (err) {
    const status = (err as { response?: { status?: number } }).response?.status
    if (status === 404) {
      return null
    }
    throw err
  }
}


export interface LibraryReportPayload {
  meta: {
    workspace_id: number
    generated_at: string
    file_count: number
    edge_count: number
  }
  hub_files: Array<{
    file_id: number
    original_name: string
    has_md: boolean
    score: number
    out_degree: number
    in_degree: number
    coref_count: number
  }>
  hub_tags: Array<{ tag: string; file_count: number }>
  hub_wiki_slugs: Array<{
    slug: string
    page_kind: string
    inbound_topic_edges: number
    file_id?: number | null
  }>
  surprising_links: Array<{
    source_file_id: number
    target_file_id: number
    source_name?: string | null
    target_name?: string | null
    edge_type: string
    top_folder_a: number
    top_folder_b: number
    source_folder_path?: string
    target_folder_path?: string
    provenance: string
  }>
  suggested_questions: Array<{
    template_id: string
    text: string
    related_slug?: string
    related_file_ids?: number[]
  }>
  governance: {
    orphan_file_count: number
    broken_link_count: number
    pending_concept_count: number
  }
}

export interface LibraryReportResponse {
  status: string
  generated_at?: string | null
  payload?: LibraryReportPayload | null
  message?: string | null
  report_id?: number | null
}

export async function getLibraryReport(): Promise<LibraryReportResponse> {
  const params = libraryReportQueryParams()
  if (params === undefined) {
    return { status: 'unavailable', message: '需要选择企业资料' }
  }
  try {
    const res = await api.get<LibraryReportResponse>('/knowledge-base/library-report', {
      params: Object.keys(params).length ? params : undefined,
      skipErrorToast: true,
    })
    return res.data
  } catch (err) {
    const status = (err as { response?: { status?: number } }).response?.status
    if (status === 404) {
      return { status: 'empty', message: '尚无资料库报告，请点击生成报告' }
    }
    throw err
  }
}

export async function refreshLibraryReport(): Promise<LibraryReportResponse> {
  const params = libraryReportQueryParams()
  if (params === undefined) {
    throw new Error('需要选择企业资料')
  }
  const res = await api.post<LibraryReportResponse>('/knowledge-base/library-report/refresh', null, {
    params: Object.keys(params).length ? params : undefined,
  })
  return res.data
}

export type QualityProjectionState = 'present' | 'partial' | 'unknown' | 'missing' | 'forbidden'

export interface QualityWorkbenchProjection {
  state: QualityProjectionState
  data?: Record<string, unknown> | null
}

export interface QualityWorkbenchFailure {
  schema_version: '187.1'
  event_key: string
  stage: string
  reason: string
  provider?: string | null
  file_id: number
  job_id: number
  request_id?: string | null
  trace_id?: string | null
  model_version?: string | null
  occurred_at: string
  retryable: boolean
  summary: string
}

export interface QualityWorkbenchResponse {
  schema_version: '187.1'
  correlation: {
    file_id: number
    job_id: number | null
    trace_id: string | null
    query_hash: string | null
    request_scope_id: string
    versions: Record<string, string | null>
  }
  extraction: QualityWorkbenchProjection
  retrieval: QualityWorkbenchProjection
  evidence: QualityWorkbenchProjection
  answer: QualityWorkbenchProjection
  failures: QualityWorkbenchFailure[]
  compatibility?: Record<string, unknown> | null
  truncated: boolean
  truncated_sections: string[]
}

export interface QualityWorkbenchTraceOption {
  trace_id: string
  status: string
  query_hash?: string | null
  created_at?: string | null
  finished_at?: string | null
}

export interface QualityWorkbenchJobOption {
  job_id: number
  status: string
  provider?: string | null
  created_at?: string | null
  updated_at?: string | null
  traces: QualityWorkbenchTraceOption[]
}

export interface QualityWorkbenchOptionsResponse {
  schema_version: '187.1'
  file_id: number
  jobs: QualityWorkbenchJobOption[]
}

export async function getQualityWorkbench(params: {
  file_id: number
  job_id?: number
  trace_id?: string
  query?: string
  version?: string
}): Promise<QualityWorkbenchResponse> {
  const res = await api.get<QualityWorkbenchResponse>('/knowledge-base/quality-workbench', {
    params,
    skipErrorToast: true,
  })
  return res.data
}

export async function getQualityWorkbenchOptions(fileId: number): Promise<QualityWorkbenchOptionsResponse> {
  const res = await api.get<QualityWorkbenchOptionsResponse>('/knowledge-base/quality-workbench/options', {
    params: { file_id: fileId },
    skipErrorToast: true,
  })
  return res.data
}
