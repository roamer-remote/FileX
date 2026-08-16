import { create } from 'zustand'
import { listWorkspaces, type WorkspaceItem } from '@/api/workspaces'
import { patchUiState } from '@/lib/uiStateSync'
import { hydrateFolderSelection, useFoldersStore } from '@/stores/foldersStore'

const STORAGE_KEY = 'filex_active_workspace_id'

function loadStoredWorkspaceId(): number | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const n = Number(raw)
    return Number.isFinite(n) ? n : null
  } catch {
    return null
  }
}

function persistWorkspaceId(id: number) {
  try {
    localStorage.setItem(STORAGE_KEY, String(id))
  } catch {
    /* ignore */
  }
  patchUiState({ active_workspace_id: id })
}

type WorkspaceState = {
  workspaces: WorkspaceItem[]
  activeWorkspaceId: number | null
  loading: boolean
  fetchWorkspaces: () => Promise<void>
  setActiveWorkspace: (id: number) => void
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  workspaces: [],
  activeWorkspaceId: loadStoredWorkspaceId(),
  loading: false,

  fetchWorkspaces: async () => {
    set({ loading: true })
    try {
      const res = await listWorkspaces()
      const workspaces = res.data
      let activeId = get().activeWorkspaceId
      const prevId = activeId
      if (!activeId || !workspaces.some((w) => w.id === activeId)) {
        const personal = workspaces.find((w) => w.kind === 'personal')
        activeId = personal?.id ?? workspaces[0]?.id ?? null
      }
      if (activeId != null) persistWorkspaceId(activeId)
      set({ workspaces, activeWorkspaceId: activeId })
      if (activeId != null && activeId !== prevId) {
        useFoldersStore.getState().switchWorkspace(prevId, activeId)
      } else if (activeId != null) {
        hydrateFolderSelection()
      }
    } finally {
      set({ loading: false })
    }
  },

  setActiveWorkspace: (id) => {
    persistWorkspaceId(id)
    set({ activeWorkspaceId: id })
  },
}))

export function getActiveWorkspaceId(): number | null {
  return useWorkspaceStore.getState().activeWorkspaceId
}
