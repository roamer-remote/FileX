import { getActiveWorkspaceId } from '@/stores/workspaceStore'

/** files API 请求附带 workspace_id（当前活跃空间）。 */
export function fileWorkspaceQueryParams(): { workspace_id?: number } | undefined {
  const wsId = getActiveWorkspaceId()
  return wsId != null ? { workspace_id: wsId } : undefined
}
