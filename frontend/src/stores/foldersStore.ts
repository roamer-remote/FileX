import { create } from 'zustand'
import {
  createFolder,
  deleteFolder,
  getFolderDirectFileCounts,
  getFolders,
  updateFolder,
  type FolderItem,
  type FolderMovePayload,
} from '@/api/folders'
import {
  ancestorFolderIds,
  buildFolderTree,
  expandedFolderIdsForSelection,
  reconcileExpandedFolderIds,
  uploadTargetFolderId,
  type FolderSelection,
  type FolderTreeNode,
} from '@/lib/folderTree'
import { getStorageToken } from '@/api/index'
import { patchFoldersUiState, patchSidebarUiState } from '@/lib/uiStateSync'
import { useFilesStore } from '@/stores/filesStore'
import { getActiveWorkspaceId } from '@/stores/workspaceStore'
import type { FolderPanelAnchor, FolderPanelMotion } from '@/lib/folderPanelMotion'
import { anchorFromElement } from '@/lib/folderPanelMotion'

const LEGACY_SELECTION_KEY = 'filex_selected_folder'
const LEGACY_EXPANDED_KEY = 'filex_folder_tree_expanded'
const SELECTION_BY_WS_KEY = 'filex_folder_selection_by_workspace'
const EXPANDED_BY_WS_KEY = 'filex_folder_expanded_by_workspace'
const PANEL_VISIBLE_BY_WS_KEY = 'filex_folder_panel_visible_by_workspace'
/** 与 SidebarNavGroup id="folders" 的 localStorage 键一致 */
export const SIDEBAR_GROUP_FOLDERS_KEY = 'filex_sidebar_group_folders'

function workspaceStorageKey(wsId: number | null): string {
  return wsId != null ? String(wsId) : 'default'
}

function parseStoredSelection(raw: string | null | undefined): FolderSelection {
  if (!raw) return 'all'
  if (raw === 'all' || raw === 'uncategorized') return raw
  const n = Number(raw)
  return Number.isFinite(n) ? n : 'all'
}

function readJsonRecord<T>(key: string): Record<string, T> {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, T>)
      : {}
  } catch {
    return {}
  }
}

function writeJsonRecord(key: string, value: Record<string, unknown>) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* ignore */
  }
}

function migrateLegacyFolderStorage(wsId: number | null) {
  const wsKey = workspaceStorageKey(wsId)
  const selections = readJsonRecord<unknown>(SELECTION_BY_WS_KEY)
  const expanded = readJsonRecord<number[]>(EXPANDED_BY_WS_KEY)
  if (
    selections[wsKey] == null &&
    expanded[wsKey] == null &&
    localStorage.getItem(LEGACY_SELECTION_KEY) == null &&
    localStorage.getItem(LEGACY_EXPANDED_KEY) == null
  ) {
    return
  }
  if (selections[wsKey] != null && expanded[wsKey] != null) {
    localStorage.removeItem(LEGACY_SELECTION_KEY)
    localStorage.removeItem(LEGACY_EXPANDED_KEY)
    return
  }

  let migrated = false
  const legacySel = localStorage.getItem(LEGACY_SELECTION_KEY)
  if (legacySel != null && selections[wsKey] == null) {
    selections[wsKey] = parseStoredSelection(legacySel)
    migrated = true
  }
  const legacyExp = localStorage.getItem(LEGACY_EXPANDED_KEY)
  if (legacyExp != null && expanded[wsKey] == null) {
    try {
      const parsed: unknown = JSON.parse(legacyExp)
      if (Array.isArray(parsed)) {
        expanded[wsKey] = parsed.filter(
          (id): id is number => typeof id === 'number' && Number.isFinite(id),
        )
        migrated = true
      }
    } catch {
      /* ignore */
    }
  }
  if (migrated) {
    writeJsonRecord(SELECTION_BY_WS_KEY, selections)
    writeJsonRecord(EXPANDED_BY_WS_KEY, expanded)
    localStorage.removeItem(LEGACY_SELECTION_KEY)
    localStorage.removeItem(LEGACY_EXPANDED_KEY)
  }
}

function loadSelectionForWorkspace(wsId: number | null): FolderSelection {
  migrateLegacyFolderStorage(wsId)
  const wsKey = workspaceStorageKey(wsId)
  const raw = readJsonRecord<unknown>(SELECTION_BY_WS_KEY)[wsKey]
  if (typeof raw === 'string') return parseStoredSelection(raw)
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw
  return 'all'
}

function persistSelectionForWorkspace(wsId: number | null, sel: FolderSelection) {
  const wsKey = workspaceStorageKey(wsId)
  const map = readJsonRecord<unknown>(SELECTION_BY_WS_KEY)
  map[wsKey] = sel
  writeJsonRecord(SELECTION_BY_WS_KEY, map)
  patchFoldersUiState()
}

function loadExpandedForWorkspace(wsId: number | null): number[] {
  migrateLegacyFolderStorage(wsId)
  const wsKey = workspaceStorageKey(wsId)
  const stored = readJsonRecord<number[]>(EXPANDED_BY_WS_KEY)[wsKey]
  if (!Array.isArray(stored)) return []
  return stored.filter((id): id is number => typeof id === 'number' && Number.isFinite(id))
}

function persistExpandedForWorkspace(wsId: number | null, ids: number[]) {
  const wsKey = workspaceStorageKey(wsId)
  const map = readJsonRecord<number[]>(EXPANDED_BY_WS_KEY)
  map[wsKey] = ids
  writeJsonRecord(EXPANDED_BY_WS_KEY, map)
  patchFoldersUiState()
}

function loadPanelVisibleForWorkspace(wsId: number | null): boolean {
  const wsKey = workspaceStorageKey(wsId)
  const raw = readJsonRecord<boolean>(PANEL_VISIBLE_BY_WS_KEY)[wsKey]
  return typeof raw === 'boolean' ? raw : true
}

function persistPanelVisibleForWorkspace(wsId: number | null, visible: boolean) {
  const wsKey = workspaceStorageKey(wsId)
  const map = readJsonRecord<boolean>(PANEL_VISIBLE_BY_WS_KEY)
  map[wsKey] = visible
  writeJsonRecord(PANEL_VISIBLE_BY_WS_KEY, map)
  patchFoldersUiState()
}

function panelStateFromVisible(visible: boolean): {
  panelOpen: boolean
  panelMinimized: boolean
} {
  return visible
    ? { panelOpen: true, panelMinimized: false }
    : { panelOpen: false, panelMinimized: true }
}

function syncFilesFilter(sel: FolderSelection) {
  useFilesStore.getState().setFolderFilter(sel)
}


function expandedForSelection(
  tree: FolderTreeNode[],
  sel: FolderSelection,
  currentExpanded: number[],
  folders: FolderItem[],
): number[] {
  if (typeof sel === 'number') {
    const fromSel = expandedFolderIdsForSelection(tree, sel, folders)
    return reconcileExpandedFolderIds(tree, [...new Set([...currentExpanded, ...fromSel])])
  }
  return reconcileExpandedFolderIds(tree, currentExpanded)
}

function normalizeSelectionForFolders(
  selection: FolderSelection,
  folders: FolderItem[],
): FolderSelection {
  if (selection === 'all' || selection === 'uncategorized') return selection
  if (folders.length === 0) return selection
  return folders.some((f) => f.id === selection) ? selection : 'all'
}

type FoldersState = {
  folders: FolderItem[]
  tree: FolderTreeNode[]
  folderFileCounts: Record<number, number>
  uncategorizedFileCount: number
  zeroAclMember: boolean
  uploadAllowed: boolean
  selected: FolderSelection
  expandedFolderIds: number[]
  loading: boolean
  folderMovePending: boolean
  panelOpen: boolean
  panelMinimized: boolean
  panelAnchor: FolderPanelAnchor | null
  panelMotion: FolderPanelMotion
  panelMinimizePending: boolean
  fetchFolders: () => Promise<void>
  refreshFolderFileCounts: () => Promise<void>
  setPanelOpen: (open: boolean) => void
  minimizePanel: () => void
  openPanel: () => void
  openPanelFromAnchor: (anchor: FolderPanelAnchor) => void
  togglePanelFromAnchor: (anchor: FolderPanelAnchor) => void
  requestMinimizePanel: (anchor?: FolderPanelAnchor | null) => void
  finishPanelMotion: () => void
  switchWorkspace: (fromWsId: number | null, toWsId: number | null) => void
  setSelected: (sel: FolderSelection) => void
  toggleExpanded: (folderId: number) => void
  mergeExpandedFolderIds: (folderIds: number[]) => void
  createFolder: (name: string, parentId?: number | null) => Promise<FolderItem>
  renameFolder: (id: number, name: string) => Promise<void>
  moveFolder: (id: number, payload: FolderMovePayload) => Promise<void>
  removeFolder: (id: number) => Promise<void>
}

export const useFoldersStore = create<FoldersState>((set, get) => ({
  folders: [],
  tree: [],
  folderFileCounts: {},
  uncategorizedFileCount: 0,
  zeroAclMember: false,
  uploadAllowed: true,
  selected: 'all',
  expandedFolderIds: [],
  loading: false,
  folderMovePending: false,
  ...panelStateFromVisible(loadPanelVisibleForWorkspace(getActiveWorkspaceId())),
  panelAnchor: null,
  panelMotion: 'idle',
  panelMinimizePending: false,

  setPanelOpen: (open) => {
    if (open) {
      persistPanelVisibleForWorkspace(getActiveWorkspaceId(), true)
      set({ panelOpen: true, panelMinimized: false, panelMotion: 'idle', panelMinimizePending: false })
      return
    }
    const triggerAnchor = anchorFromElement(document.querySelector('.folder-panel-trigger'))
    if (triggerAnchor) {
      get().requestMinimizePanel(triggerAnchor)
    } else {
      // 侧栏未挂载（如纯 API 调试页）：无法取锚点，跳过退出动画直接最小化
      persistPanelVisibleForWorkspace(getActiveWorkspaceId(), false)
      set({
        panelOpen: false,
        panelMinimized: true,
        panelMotion: 'idle',
        panelAnchor: null,
        panelMinimizePending: false,
      })
    }
  },
  minimizePanel: () => {
    persistPanelVisibleForWorkspace(getActiveWorkspaceId(), false)
    set({
      panelOpen: false,
      panelMinimized: true,
      panelMotion: 'idle',
      panelAnchor: null,
      panelMinimizePending: false,
    })
  },
  openPanel: () => {
    persistPanelVisibleForWorkspace(getActiveWorkspaceId(), true)
    const anchor = anchorFromElement(document.querySelector('.folder-panel-trigger'))
    if (anchor) {
      get().openPanelFromAnchor(anchor)
    } else {
      set({ panelOpen: true, panelMinimized: false, panelMotion: 'idle' })
    }
  },
  openPanelFromAnchor: (anchor) => {
    persistPanelVisibleForWorkspace(getActiveWorkspaceId(), true)
    set({ panelOpen: true, panelMinimized: false, panelAnchor: anchor, panelMotion: 'enter' })
  },
  togglePanelFromAnchor: (anchor) => {
    const { panelOpen, panelMotion } = get()
    if (panelOpen && panelMotion !== 'exit') {
      get().requestMinimizePanel(anchor)
    } else {
      get().openPanelFromAnchor(anchor)
    }
  },
  requestMinimizePanel: (anchor) => {
    const resolved = anchor ?? get().panelAnchor
    set({
      panelOpen: false,
      panelMotion: 'exit',
      panelMinimizePending: true,
      ...(resolved ? { panelAnchor: resolved } : {}),
    })
  },
  finishPanelMotion: () => {
    const { panelMotion, panelOpen, panelMinimizePending } = get()
    if (panelMotion === 'exit' && !panelOpen) {
      if (panelMinimizePending) {
        persistPanelVisibleForWorkspace(getActiveWorkspaceId(), false)
      }
      set({
        panelMotion: 'idle',
        panelAnchor: null,
        panelMinimized: panelMinimizePending,
        panelMinimizePending: false,
      })
    } else if (panelMotion === 'enter') {
      persistPanelVisibleForWorkspace(getActiveWorkspaceId(), true)
      set({ panelMotion: 'idle', panelMinimized: false, panelMinimizePending: false })
    }
  },

  switchWorkspace: (fromWsId, toWsId) => {
    if (fromWsId != null && fromWsId !== toWsId) {
      const { selected, expandedFolderIds, panelOpen, panelMotion } = get()
      persistSelectionForWorkspace(fromWsId, selected)
      persistExpandedForWorkspace(fromWsId, expandedFolderIds)
      if (panelMotion === 'idle') {
        persistPanelVisibleForWorkspace(fromWsId, panelOpen)
      }
    }
    const selected = loadSelectionForWorkspace(toWsId)
    const expandedFolderIds = loadExpandedForWorkspace(toWsId)
    set({
      selected,
      expandedFolderIds,
      ...panelStateFromVisible(loadPanelVisibleForWorkspace(toWsId)),
      panelMotion: 'idle',
      panelAnchor: null,
      panelMinimizePending: false,
    })
    syncFilesFilter(selected)
  },

  fetchFolders: async () => {
    const wsIdAtStart = getActiveWorkspaceId()
    if (wsIdAtStart == null) return

    set({ loading: true })
    try {
      const res = await getFolders({ workspace_id: wsIdAtStart })
      const wsId = getActiveWorkspaceId()
      if (wsId !== wsIdAtStart) {
        if (wsId != null) await get().fetchFolders()
        return
      }
      const folders = res.data
      const tree = buildFolderTree(folders)
      const storedSelection = loadSelectionForWorkspace(wsId)
      const selected = normalizeSelectionForFolders(storedSelection, folders)
      const expandedFolderIds = expandedForSelection(
        tree,
        selected,
        loadExpandedForWorkspace(wsId),
        folders,
      )
      persistExpandedForWorkspace(wsId, expandedFolderIds)
      persistSelectionForWorkspace(wsId, selected)
      const countsRes = await getFolderDirectFileCounts({
        workspace_id: wsIdAtStart,
        upload_folder_id: uploadFolderIdForCapability(selected),
      })
      set({
        folders,
        tree,
        expandedFolderIds,
        selected,
        folderFileCounts: countsRes.data.folder_file_counts ?? {},
        uncategorizedFileCount: countsRes.data.uncategorized_file_count ?? 0,
        zeroAclMember: countsRes.data.zero_acl_member === true,
        uploadAllowed: countsRes.data.upload_allowed !== false,
      })
      syncFilesFilter(selected)
    } finally {
      set({ loading: false })
    }
  },

  refreshFolderFileCounts: async () => {
    try {
      const wsId = getActiveWorkspaceId()
      const { selected } = get()
      const res = await getFolderDirectFileCounts({
        workspace_id: wsId ?? undefined,
        upload_folder_id: uploadFolderIdForCapability(selected),
      })
      set({
        folderFileCounts: res.data.folder_file_counts ?? {},
        uncategorizedFileCount: res.data.uncategorized_file_count ?? 0,
        zeroAclMember: res.data.zero_acl_member === true,
        uploadAllowed: res.data.upload_allowed !== false,
      })
    } catch {
      /* ignore — 目录树计数为辅助信息 */
    }
  },

  setSelected: (sel) => {
    const wsId = getActiveWorkspaceId()
    const { tree, expandedFolderIds: currentExpanded, folders } = get()
    const expandedFolderIds = expandedForSelection(tree, sel, currentExpanded, folders)
    persistSelectionForWorkspace(wsId, sel)
    persistExpandedForWorkspace(wsId, expandedFolderIds)
    set({ selected: sel, expandedFolderIds })
    syncFilesFilter(sel)
    void get().refreshFolderFileCounts()
  },

  toggleExpanded: (folderId) => {
    set((s) => {
      const wsId = getActiveWorkspaceId()
      const has = s.expandedFolderIds.includes(folderId)
      const expandedFolderIds = has
        ? s.expandedFolderIds.filter((id) => id !== folderId)
        : [...s.expandedFolderIds, folderId]
      persistExpandedForWorkspace(wsId, expandedFolderIds)
      return { expandedFolderIds }
    })
  },

  mergeExpandedFolderIds: (folderIds) => {
    set((s) => {
      const wsId = getActiveWorkspaceId()
      const expandedFolderIds = reconcileExpandedFolderIds(s.tree, [
        ...s.expandedFolderIds,
        ...folderIds,
      ])
      persistExpandedForWorkspace(wsId, expandedFolderIds)
      return { expandedFolderIds }
    })
  },

  createFolder: async (name, parentId) => {
    const wsId = getActiveWorkspaceId()
    const res = await createFolder(name, parentId ?? null, wsId ?? undefined)
    await get().fetchFolders()
    if (parentId != null) {
      const { folders, tree } = get()
      const expandedFolderIds = reconcileExpandedFolderIds(tree, [
        ...ancestorFolderIds(folders, parentId),
        parentId,
      ])
      persistExpandedForWorkspace(wsId, expandedFolderIds)
      set({ expandedFolderIds })
    }
    return res.data
  },

  renameFolder: async (id, name) => {
    await updateFolder(id, { name })
    await get().fetchFolders()
  },

  moveFolder: async (id, payload) => {
    set({ folderMovePending: true })
    try {
      await updateFolder(id, payload)
      await get().fetchFolders()
    } finally {
      set({ folderMovePending: false })
    }
  },

  removeFolder: async (id) => {
    const wsId = getActiveWorkspaceId()
    const { selected } = get()
    await deleteFolder(id)
    await get().fetchFolders()
    if (selected === id) {
      get().setSelected('all')
    } else {
      persistSelectionForWorkspace(wsId, get().selected)
    }
  },
}))

/** 打开侧栏「目录」分组（登录/刷新后目录区默认展开） */
export function openFolderSidebarGroup() {
  try {
    localStorage.setItem(SIDEBAR_GROUP_FOLDERS_KEY, '1')
  } catch {
    /* ignore */
  }
  patchSidebarUiState()
}

/** 登录后或会话校验通过后恢复目录筛选；未登录时仅恢复本地 UI 状态，不请求文件列表 */
export function hydrateFolderSelection() {
  openFolderSidebarGroup()
  const wsId = getActiveWorkspaceId()
  migrateLegacyFolderStorage(wsId)
  const selected = loadSelectionForWorkspace(wsId)
  const expandedFolderIds = loadExpandedForWorkspace(wsId)
  useFoldersStore.setState({
    selected,
    expandedFolderIds,
    ...panelStateFromVisible(loadPanelVisibleForWorkspace(wsId)),
    panelMotion: 'idle',
    panelAnchor: null,
    panelMinimizePending: false,
  })
  useFilesStore.setState({ folderFilter: selected, page: 1 })
  if (getStorageToken()) {
    syncFilesFilter(selected)
  }
}

function uploadFolderIdForCapability(selection: FolderSelection): number | undefined {
  const target = uploadTargetFolderId(selection)
  return target ?? undefined
}
