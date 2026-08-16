import api, { getStorageToken } from './index'
import type { AxiosProgressEvent } from 'axios'
import { fileWorkspaceQueryParams } from '@/lib/fileWorkspaceParams'

export interface FileTagAnchorItem {
  anchor_id: string
  tag: string
  occurrence_index: number
  start_offset: number
  end_offset: number
}

export interface FileItem {
  id: number
  filename: string
  original_name: string
  file_size: number
  mime_type: string
  folder_id: number | null
  workspace_id?: number | null
  publish_status?: string
  user_id: number
  username?: string
  created_at: string
  updated_at?: string | null
  md5_hash?: string
  has_md?: boolean
  /** 笔记文件存在且内容 strip 后非空 */
  md_has_content?: boolean
  /** 上传时与同用户下已有文件内容（MD5）相同，未新建记录 */
  deduplicated?: boolean
  /** 列表用缩略图是否已生成（后端磁盘） */
  has_thumbnail?: boolean
  tags?: string[]
  /** 主 Markdown 文件标签在正文中的锚点（由后端在保存标签时重建） */
  tag_anchors?: FileTagAnchorItem[]
  index_status?: string
  indexed_at?: string | null
  chunk_count?: number
  index_error?: string | null
  kb_post_status?: string
  kb_post_error?: string | null
  extract_status?: string
  extracted_at?: string | null
  extract_error?: string | null
  extract_engine?: string | null
  page_kind?: string
  wiki_slug?: string | null
  /** 旧版 Office 规范化副本 MIME；有值时浏览器可在线预览 */
  preview_mime_type?: string | null
  /** 当前用户是否可修改/移动/标签/笔记 */
  can_write?: boolean
  /** 当前用户是否可删除 */
  can_manage?: boolean
  /** OKF Concept path（新上传资料） */
  okf_concept_path?: string | null
  /** OKF frontmatter type */
  okf_type?: string | null
  /** OKF frontmatter 摘要（不含 type） */
  okf_metadata?: Record<string, unknown> | null
}

/** GET /api/files?folder_id=0：仅未分类 */
export const FOLDER_ID_UNCATEGORIZED = 0

export interface FileListParams {
  workspace_id?: number
  folder_id?: number | null
  search?: string
  tag?: string
  /** 与 tag 同时传入：仅返回同时带有两个标签的文件（AND） */
  tag2?: string
  /** 按最后更新时间（无则回退创建时间）：desc 新在前，asc 旧在前 */
  sort_time?: 'desc' | 'asc'
  /** 按文件名排序（忽略大小写）；传入时优先于 sort_time */
  sort_name?: 'desc' | 'asc'
  page?: number
  page_size?: number
}

export interface FileListResponse {
  items: FileItem[]
  total: number
  page: number
  page_size: number
}

export interface FileTypeStatItem {
  key: string
  count: number
  percent: number
}

export interface FileStatsPayload {
  total_files: number
  total_characters: number
  indexed_count: number
  tag_count: number
  document_type_count: number
  file_types: FileTypeStatItem[]
}

export interface TagGraphNode {
  id: string
  name: string
  value: number
}

export interface TagGraphLink {
  source: string
  target: string
  value: number
}

export interface TagGraphFileGroup {
  file_id: number
  label: string
  tags: string[]
}

export interface TagGraphResponse {
  nodes: TagGraphNode[]
  links: TagGraphLink[]
  file_groups: TagGraphFileGroup[]
  truncated: boolean
  total_files_with_tags: number
}

export interface TagHeatmapResponse {
  tags: string[]
  matrix: number[][]
}

export function getFiles(params: FileListParams = {}) {
  return api.get<FileListResponse>('/files', { params })
}

export function getFileStats() {
  return api.get<FileStatsPayload>('/files/stats')
}

export function getFileById(id: number) {
  return api.get<FileItem>(`/files/${id}`)
}

export function getTagGraph() {
  return api.get<TagGraphResponse>('/files/tags/graph')
}

export function getTagHeatmap() {
  return api.get<TagHeatmapResponse>('/files/tags/heatmap')
}

export function uploadFile(formData: FormData, onProgress?: (e: AxiosProgressEvent) => void) {
  return api.post<FileItem>('/files/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress,
  })
}

export async function deleteFile(id: number, options?: { deferKbIndexSync?: boolean }) {
  const params = options?.deferKbIndexSync ? { defer_kb_index_sync: true } : undefined
  const maxAttempts = 3
  let lastError: unknown
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await api.delete(`/files/${id}`, { params })
    } catch (err) {
      lastError = err
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409 && attempt < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, 2000 * attempt))
        continue
      }
      throw err
    }
  }
  throw lastError
}

export function updateFile(id: number, data: { filename?: string; folder_id?: number | null }) {
  return api.put(`/files/${id}`, data)
}

export function getDownloadUrl(id: number): string {
  const token = getStorageToken()
  return `/api/files/${id}/download?token=${token}`
}

export function parseContentDispositionFilename(header: string | null): string | null {
  if (!header) return null
  const encoded = /filename\*=(?:UTF-8''|utf-8'')([^;\s]+)/i.exec(header)
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1].replace(/\+/g, ' '))
    } catch {
      return encoded[1]
    }
  }
  const quoted = /filename="((?:[^"\\]|\\.)*)"/i.exec(header)
  if (quoted?.[1]) return quoted[1].replace(/\\"/g, '"')
  const plain = /filename=([^;\s]+)/i.exec(header)
  if (plain?.[1]) return plain[1].replace(/^["']|["']$/g, '')
  return null
}

/** fetch + Blob 触发本页保存，避免 window.open 新开标签 */
export async function downloadAuthenticatedFile(url: string, fallbackFilename: string): Promise<void> {
  const token = getStorageToken()
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const blob = await res.blob()
  const name = parseContentDispositionFilename(res.headers.get('Content-Disposition')) ?? fallbackFilename
  const objectUrl = URL.createObjectURL(blob)
  try {
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = name
    a.rel = 'noopener noreferrer'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}

export function getPreviewUrl(id: number): string {
  const token = getStorageToken()
  return `/api/files/${id}/preview?token=${token}`
}

export function getThumbnailUrl(id: number): string {
  const token = getStorageToken()
  return `/api/files/${id}/thumbnail?token=${token}`
}

export function getExtractAssetUrl(fileId: number, assetKey: string): string {
  return `/api/files/${fileId}/extract-assets/${encodeURIComponent(assetKey)}`
}

export interface SignedExtractAssetItem {
  asset_key: string
  url: string
  expires_at: number
}

export interface ExtractAssetSignResponse {
  items: SignedExtractAssetItem[]
  expires_at: number
}

export function signExtractAssets(
  fileId: number,
  assetKeys: string[],
  options?: { signal?: AbortSignal },
) {
  return api.post<ExtractAssetSignResponse>(
    `/files/${fileId}/extract-assets/sign`,
    { asset_keys: assetKeys },
    { signal: options?.signal },
  )
}

export function getMdContentUrl(md5Hash: string): string {
  const token = getStorageToken()
  return `/api/external/md-content/${md5Hash}?token=${token}`
}

export function uploadFileMd(fileId: number, content: string) {
  return api.put(`/files/${fileId}/md`, { content }, { params: fileWorkspaceQueryParams() })
}

export function getFileMd(fileId: number) {
  return api.get(`/files/${fileId}/md`, { responseType: 'text', params: fileWorkspaceQueryParams() })
}

export function deleteFileMd(fileId: number) {
  return api.delete(`/files/${fileId}/md`, { params: fileWorkspaceQueryParams() })
}

export function listMyTags() {
  return api.get<string[]>('/files/tags')
}

export function replaceFileTags(fileId: number, tags: string[]) {
  return api.put<string[]>(`/files/${fileId}/tags`, { tags })
}

export interface WikiLinkOutItem {
  target_file_id: number | null
  target_name: string | null
  target_wiki_slug: string | null
  link_kind: string
  link_text: string | null
  anchor_id: string
  start_offset: number
  end_offset: number
  broken: boolean
  broken_reason: string | null
}

export interface WikiLinkBackItem {
  source_file_id: number
  source_name: string
  link_text: string | null
  anchor_id: string
  broken: boolean
}

export interface WikiCorefPeerItem {
  file_id: number
  source_name: string
  shared_wiki_slugs: string[]
}

export interface WikiLinksResponse {
  file_id: number
  outlinks: WikiLinkOutItem[]
  backlinks: WikiLinkBackItem[]
  outlink_count: number
  backlink_count: number
  coref_files: WikiCorefPeerItem[]
  coref_count: number
}

export function getFileWikiLinks(
  fileId: number,
  opts?: { dedupe?: boolean; sourceFileDirectOnly?: boolean },
) {
  const params: Record<string, unknown> = { ...fileWorkspaceQueryParams() }
  if (opts?.dedupe === false) params.dedupe = false
  if (opts?.sourceFileDirectOnly) params.source_file_direct_only = true
  return api.get<WikiLinksResponse>(`/files/${fileId}/wiki-links`, { params })
}

export interface PipelineTraceStep {
  key: string
  title: string
  status: string
  detail?: string | null
  error_message?: string | null
  log_deep_link?: string | null
  occurred_at?: string | null
  // 索引效率监控字段（针对大文件如 340 的检索建立耗时）
  embed_ms?: number | null
  persist_ms?: number | null
  post_index_ms?: number | null
  post_entity_ms?: number | null
  post_sag_ms?: number | null
  post_raptor_ms?: number | null
  large_pdf?: boolean | null
  post_skip_reason?: string | null
}

export interface FilePipelineTraceResponse {
  file_id: number
  filename: string
  trace_provider?: string | null
  global_default_provider: string
  chunk_count: number
  has_md_notes: boolean
  steps: PipelineTraceStep[]
}

export function getFilePipelineTrace(fileId: number) {
  return api.get<FilePipelineTraceResponse>(`/files/${fileId}/pipeline-trace`, {
    params: fileWorkspaceQueryParams(),
  })
}

export interface OkfMetaResponse {
  okf_concept_path: string | null
  okf_type: string | null
  frontmatter: Record<string, unknown>
}

export interface OkfMetaUpdatePayload {
  type?: string
  title?: string
  description?: string
  tags?: string[]
  okf_concept_path?: string
}

export function getFileOkfRaw(fileId: number) {
  return api.get(`/files/${fileId}/okf`, { responseType: 'text', params: fileWorkspaceQueryParams() })
}

export function getFileOkfMeta(fileId: number) {
  return api.get<OkfMetaResponse>(`/files/${fileId}/okf/meta`, { params: fileWorkspaceQueryParams() })
}

export function putFileOkfMeta(fileId: number, payload: OkfMetaUpdatePayload) {
  return api.put(`/files/${fileId}/okf/meta`, payload, { params: fileWorkspaceQueryParams() })
}
