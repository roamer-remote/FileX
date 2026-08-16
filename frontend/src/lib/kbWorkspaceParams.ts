import { getActiveWorkspaceId } from '@/stores/workspaceStore'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'

export function isSharedWorkspacesEnabled(): boolean {
  const settings = useSystemSettingsStore.getState()
  return settings.loaded ? settings.shared_workspaces_enabled === true : false
}

/** 共享空间开启时附带 workspace_id；关闭时不传（后端默认个人空间）。 */
export function kbWorkspaceQueryParams(): { workspace_id?: number } | undefined {
  const sharedOn = isSharedWorkspacesEnabled()
  if (!sharedOn) return undefined
  const wsId = getActiveWorkspaceId()
  return wsId != null ? { workspace_id: wsId } : undefined
}

/** library-report 始终需要 workspace 上下文；共享空间关闭时由后端默认个人空间。 */
export function libraryReportQueryParams(): { workspace_id?: number } | undefined {
  const sharedOn = isSharedWorkspacesEnabled()
  const wsId = getActiveWorkspaceId()
  if (wsId != null) return { workspace_id: wsId }
  if (sharedOn) return undefined
  return {}
}

export function resolveActiveWorkspaceId(): number | null {
  return getActiveWorkspaceId()
}
