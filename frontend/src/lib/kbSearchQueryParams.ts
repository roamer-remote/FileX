import {
  isSharedWorkspacesEnabled,
  kbWorkspaceQueryParams as buildKbWorkspaceQueryParams,
} from '@/lib/kbWorkspaceParams'

/** 向量检索 query：共享空间关闭时不传 workspace_id / cross_workspace。 */
export function kbSearchQueryParams(cross_workspace?: boolean) {
  const sharedOn = isSharedWorkspacesEnabled()
  const params: Record<string, string | number | boolean> = {}
  if (sharedOn) {
    const base = buildKbWorkspaceQueryParams()
    if (base?.workspace_id != null) params.workspace_id = base.workspace_id
  }
  if (cross_workspace && sharedOn) params.cross_workspace = true
  return Object.keys(params).length ? params : undefined
}
