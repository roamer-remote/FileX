import api from './index'

export interface AdminSkillFileItem {
  file_id: string
  label: string
  path: string
  kind: string
  group: string
  etag: string
  sha256: string
  size_bytes: number
  updated_at: string
}

export interface AdminSkillFilesListResponse {
  writable: boolean
  data_ready?: boolean
  cache_enabled?: boolean
  skill_version: string | null
  disk_skill_version: string | null
  bootstrap_min_version: string | null
  files: AdminSkillFileItem[]
}

export interface AdminSkillFileResponse {
  file_id: string
  content: string
  etag: string
  sha256: string
  kind: string
  path: string
  label: string
  size_bytes: number
  updated_at: string
}

export interface AdminSkillSyncFromDiskResponse {
  ok: boolean
  data_ready: boolean
  skill_dir: string | null
  synced: string[]
  added: string[]
  updated: string[]
  removed: string[]
  reason: string | null
}

function enc(fileId: string) {
  return encodeURIComponent(fileId)
}

export function listAdminSkillFiles() {
  return api.get<AdminSkillFilesListResponse>('/admin/skill/files')
}

export function getAdminSkillFile(fileId: string) {
  return api.get<AdminSkillFileResponse>(`/admin/skill/files/${enc(fileId)}`)
}

export function syncSkillFromDisk() {
  return api.post<AdminSkillSyncFromDiskResponse>('/admin/skill/sync-from-disk')
}
