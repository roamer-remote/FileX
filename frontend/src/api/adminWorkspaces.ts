import api, { getStorageToken } from './index'
import type { FileListResponse } from './files'

const adminOpts = { skipErrorToast: true } as const

export type AdminWorkspaceItem = {
  id: number
  name: string
  slug: string
  kind: 'personal' | 'shared'
  owner_user_id: number | null
  owner_username: string | null
  member_count: number
  created_at: string
}

export type WorkspaceMemberItem = {
  user_id: number
  username: string
  role: string
}

export type ResourceGrantItem = {
  id: number
  resource_type: 'file' | 'folder'
  resource_id: number
  grantee_user_id: number
  grantee_username: string
  permission: 'view' | 'edit'
  created_at: string
}

export type KbSearchAuditItem = {
  id: number
  user_id: number
  username: string
  workspace_id: number
  query: string
  hit_file_ids: string | null
  top_k: number
  created_at: string
}

export type MdVersionItem = {
  id: number
  file_id: number
  version: number
  content: string
  created_by_user_id: number | null
  created_at: string
}

export type AdminUserOption = {
  id: number
  username: string
  is_admin?: boolean
  is_active?: boolean
}

export function listAdminWorkspaces() {
  return api.get<AdminWorkspaceItem[]>('/admin/workspaces', adminOpts)
}

export function createAdminWorkspace(name: string, ownerUserId: number) {
  return api.post<AdminWorkspaceItem>(
    '/admin/workspaces',
    { name, owner_user_id: ownerUserId },
    adminOpts,
  )
}

export function updateAdminWorkspace(id: number, name: string) {
  return api.put<AdminWorkspaceItem>(`/admin/workspaces/${id}`, { name }, adminOpts)
}

export function deleteAdminWorkspace(id: number) {
  return api.delete(`/admin/workspaces/${id}`, adminOpts)
}

export function listWorkspaceMembers(workspaceId: number) {
  return api.get<WorkspaceMemberItem[]>(`/admin/workspaces/${workspaceId}/members`, adminOpts)
}

export function upsertWorkspaceMember(workspaceId: number, userId: number, role: string) {
  return api.post<WorkspaceMemberItem>(
    `/admin/workspaces/${workspaceId}/members`,
    {
      user_id: userId,
      role,
    },
    adminOpts,
  )
}

export function removeWorkspaceMember(workspaceId: number, userId: number) {
  return api.delete(`/admin/workspaces/${workspaceId}/members/${userId}`, adminOpts)
}

export function listWorkspaceGrants(workspaceId: number) {
  return api.get<ResourceGrantItem[]>(`/admin/workspaces/${workspaceId}/grants`, adminOpts)
}

export function createWorkspaceGrant(
  workspaceId: number,
  body: {
    resource_type: 'file' | 'folder'
    resource_id: number
    grantee_user_id: number
    permission: 'view' | 'edit'
  },
) {
  return api.post<ResourceGrantItem>(`/admin/workspaces/${workspaceId}/grants`, body, adminOpts)
}

export function deleteWorkspaceGrant(workspaceId: number, grantId: number) {
  return api.delete(`/admin/workspaces/${workspaceId}/grants/${grantId}`, adminOpts)
}

export function listWorkspaceSearchAudit(workspaceId: number, limit = 100) {
  return api.get<KbSearchAuditItem[]>(`/admin/workspaces/${workspaceId}/audit/search`, {
    ...adminOpts,
    params: { limit },
  })
}

export async function downloadWorkspaceSearchAuditExport(workspaceId: number) {
  const res = await api.get<string>(`/admin/workspaces/${workspaceId}/audit/search/export`, {
    ...adminOpts,
    responseType: 'text',
  })
  const blob = new Blob([res.data], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `kb-search-audit-ws-${workspaceId}.tsv`
  a.click()
  URL.revokeObjectURL(url)
}

export async function downloadGlobalSearchAuditExport(workspaceId?: number) {
  const res = await api.get<string>('/admin/audit/search-export', {
    ...adminOpts,
    params: workspaceId != null ? { workspace_id: workspaceId } : undefined,
    responseType: 'text',
  })
  const blob = new Blob([res.data], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = workspaceId != null ? `kb-search-audit-ws-${workspaceId}.tsv` : 'kb-search-audit-all.tsv'
  a.click()
  URL.revokeObjectURL(url)
}

export function getAdminUsers() {
  return api.get<{ items: AdminUserOption[] }>('/admin/users', { ...adminOpts, params: { page: 1, page_size: 100 } })
}

export function getAdminFiles(params: {
  workspace_id?: number
  page?: number
  page_size?: number
  search?: string
}) {
  return api.get<FileListResponse>('/admin/files', { ...adminOpts, params })
}

export function setAdminFilePublishStatus(fileId: number, publishStatus: 'draft' | 'published') {
  return api.put<{ file_id: number; publish_status: string }>(
    `/admin/files/${fileId}/publish-status`,
    { publish_status: publishStatus },
    adminOpts,
  )
}

export function listAdminMdVersions(fileId: number) {
  return api.get<MdVersionItem[]>(`/admin/files/${fileId}/md/versions`, adminOpts)
}

export function getAdminFileMd(fileId: number) {
  return api.get<string>(`/admin/files/${fileId}/md`, { ...adminOpts, responseType: 'text' })
}

export function restoreAdminMdVersion(fileId: number, versionId: number) {
  return api.post<{ file_id: number; restored_version: number }>(
    `/admin/files/${fileId}/md/restore-version`,
    { version_id: versionId },
    adminOpts,
  )
}
