import api, { getStorageToken } from './index'

const adminOpts = { skipErrorToast: true } as const

export type ExternalSyncWorkspaceOption = {
  id: number
  name: string
  kind: string
}

export type ExternalSyncSource = {
  id: number
  workspace_id: number
  user_id: number
  provider: string
  is_active: boolean
  delete_policy: string
  config_public_json: Record<string, unknown>
  secret_preview: string
  last_sync_at: string | null
  created_at: string | null
  updated_at: string | null
}

export function listExternalSyncWorkspaces() {
  return api.get<ExternalSyncWorkspaceOption[]>('/admin/external-sync/workspaces', adminOpts)
}

export function listExternalSyncSources() {
  return api.get<ExternalSyncSource[]>('/admin/external-sync/sources', adminOpts)
}

export function createExternalSyncSource(body: {
  workspace_id: number
  provider: string
  secret: string
  config_public_json: Record<string, unknown>
  delete_policy: string
  is_active: boolean
}) {
  return api.post<ExternalSyncSource>('/admin/external-sync/sources', body, adminOpts)
}

export function updateExternalSyncSource(
  id: number,
  body: Partial<{
    workspace_id: number
    config_public_json: Record<string, unknown>
    delete_policy: string
    is_active: boolean
  }>,
) {
  return api.put<ExternalSyncSource>(`/admin/external-sync/sources/${id}`, body, adminOpts)
}

export function rotateExternalSyncSecret(id: number, secret: string) {
  return api.post<ExternalSyncSource>(
    `/admin/external-sync/sources/${id}/rotate-secret`,
    { secret },
    adminOpts,
  )
}

export function testExternalSyncConnection(id: number) {
  return api.post<{ ok: boolean; database_id: string; title?: string | null }>(
    `/admin/external-sync/sources/${id}/test-connection`,
    {},
    adminOpts,
  )
}

export function syncExternalSyncNow(id: number) {
  return api.post<{ run_id: string; status: string }>(
    `/admin/external-sync/sources/${id}/sync-now`,
    {},
    adminOpts,
  )
}

export function getExternalSyncDeletePolicyHint() {
  return api.get<{ hint: string }>('/admin/external-sync/meta/delete-policy-hint', adminOpts)
}
