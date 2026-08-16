import api from './index'

export interface FolderItem {
  id: number
  name: string
  parent_id: number | null
  sort_order: number
  user_id: number
  created_at: string
}

export type FolderMovePayload = {
  name?: string
  parent_id?: number | null
  sort_order?: number
}

export type FolderDirectFileCounts = {
  uncategorized_file_count: number
  folder_file_counts: Record<number, number>
  zero_acl_member?: boolean
  upload_allowed?: boolean
}

export function getFolderDirectFileCounts(params?: {
  workspace_id?: number
  upload_folder_id?: number | null
}) {
  return api.get<FolderDirectFileCounts>('/folders/direct-file-counts', { params })
}

export function getFolders(params?: { parent_id?: number | null; workspace_id?: number }) {
  return api.get<FolderItem[]>('/folders', { params })
}

export function createFolder(name: string, parent_id?: number | null, workspace_id?: number) {
  return api.post<FolderItem>('/folders', { name, parent_id }, { params: { workspace_id } })
}

export function updateFolder(id: number, payload: FolderMovePayload | { name: string }) {
  return api.put<FolderItem>(`/folders/${id}`, payload)
}

export function deleteFolder(id: number) {
  return api.delete(`/folders/${id}`)
}
