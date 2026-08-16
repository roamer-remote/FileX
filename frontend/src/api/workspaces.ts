import api from './index'

export type WorkspaceItem = {
  id: number
  name: string
  slug: string
  kind: 'personal' | 'shared'
  owner_user_id: number | null
  my_role: string
  created_at: string
}

export function listWorkspaces() {
  return api.get<WorkspaceItem[]>('/workspaces')
}

export function createWorkspace(name: string) {
  return api.post<WorkspaceItem>('/workspaces', { name })
}
