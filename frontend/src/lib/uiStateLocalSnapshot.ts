import type {
  AdminOrgState,
  FolderSelection,
  FoldersState,
  PanelPos,
  PanelSize,
  UserUiStateV1,
} from '@/lib/uiStateTypes'
import { defaultUiStateV1 } from '@/lib/uiStateTypes'

const LEGACY_KEYS = [
  'filex_active_workspace_id',
  'filex_folder_selection_by_workspace',
  'filex_folder_expanded_by_workspace',
  'filex_folder_panel_visible_by_workspace',
  'filex_getting_started_seen',
  'filex_sidebar_collapsed',
  'filex_theme',
  'filex_accent',
  'filex_locale',
  'filex_auth_method',
  'filex_remember_me',
  'filex_kb_search_cross_workspace',
  'filex_kb_eval_filename_boost',
  'filex_kb_eval_modality_boost',
  'filex_kb_eval_hybrid',
  'filex_kb_eval_query_expansion',
  'filex_kb_eval_evidence_mode',
  'filex_mq_pet_pos',
  'filex_kb_toolbar_pos',
  'filex_kb_toolbar_collapsed',
  'filex_selected_folder',
  'filex_folder_tree_expanded',
] as const

const PANEL_POS_PREFIX = 'filex_folder_panel_pos_'
const PANEL_SIZE_PREFIX = 'filex_folder_panel_size_'
const SIDEBAR_GROUP_PREFIX = 'filex_sidebar_group_'
const ADMIN_ORG_KEY = 'filex_admin_org'

/** 与 foldersStore / FolderFloatingPanel 一致的工作空间 localStorage 键段 */
export function workspaceStorageKeyForUi(wsId: number | null): string {
  return wsId != null ? String(wsId) : 'default'
}

export function panelPosLocalKey(wsId: number | null): string {
  return `${PANEL_POS_PREFIX}${workspaceStorageKeyForUi(wsId)}`
}

export function panelSizeLocalKey(wsId: number | null): string {
  return `${PANEL_SIZE_PREFIX}${workspaceStorageKeyForUi(wsId)}`
}

export type PanelSizeLocal = { width: number; height: number }

export function readPanelPosFromLocal(wsId: number | null): PanelPos | null {
  try {
    const raw = localStorage.getItem(panelPosLocalKey(wsId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as { x?: number; y?: number }
    if (typeof parsed?.x === 'number' && typeof parsed?.y === 'number') {
      return { x: parsed.x, y: parsed.y }
    }
  } catch {
    /* ignore */
  }
  return null
}

export function readPanelSizeFromLocal(wsId: number | null): PanelSizeLocal | null {
  try {
    const raw = localStorage.getItem(panelSizeLocalKey(wsId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as { width?: number; height?: number; w?: number; h?: number }
    const width = parsed.width ?? parsed.w
    const height = parsed.height ?? parsed.h
    if (typeof width === 'number' && typeof height === 'number') {
      return { width, height }
    }
  } catch {
    /* ignore */
  }
  return null
}

export function writePanelPosToLocal(wsId: number | null, pos: PanelPos): void {
  try {
    localStorage.setItem(
      panelPosLocalKey(wsId),
      JSON.stringify({ x: Math.round(pos.x), y: Math.round(pos.y) }),
    )
  } catch {
    /* ignore */
  }
}

export function writePanelSizeToLocal(wsId: number | null, size: PanelSizeLocal): void {
  try {
    localStorage.setItem(
      panelSizeLocalKey(wsId),
      JSON.stringify({ width: Math.round(size.width), height: Math.round(size.height) }),
    )
  } catch {
    /* ignore */
  }
}

/** applyUiStateToLocal 完成后派发，供 FolderFloatingPanel 等重新读取 localStorage */
export const UI_STATE_LOCAL_APPLIED_EVENT = 'filex:ui-state-local-applied'

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

function parseSelection(raw: unknown): FolderSelection {
  if (raw === 'all' || raw === 'uncategorized') return raw
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw
  if (typeof raw === 'string') {
    if (raw === 'all' || raw === 'uncategorized') return raw
    const n = Number(raw)
    if (Number.isFinite(n)) return n
  }
  return 'all'
}

function readPanelMaps(): Pick<FoldersState, 'panel_pos_by_ws' | 'panel_size_by_ws'> {
  const panel_pos_by_ws: Record<string, PanelPos> = {}
  const panel_size_by_ws: Record<string, PanelSize> = {}
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (!key) continue
      if (key.startsWith(PANEL_POS_PREFIX)) {
        const wsKey = key.slice(PANEL_POS_PREFIX.length) || 'default'
        const raw = localStorage.getItem(key)
        if (!raw) continue
        const parsed = JSON.parse(raw) as { x?: number; y?: number }
        if (typeof parsed?.x === 'number' && typeof parsed?.y === 'number') {
          panel_pos_by_ws[wsKey] = { x: Math.round(parsed.x), y: Math.round(parsed.y) }
        }
      } else if (key.startsWith(PANEL_SIZE_PREFIX)) {
        const wsKey = key.slice(PANEL_SIZE_PREFIX.length) || 'default'
        const raw = localStorage.getItem(key)
        if (!raw) continue
        const parsed = JSON.parse(raw) as { width?: number; height?: number; w?: number; h?: number }
        const w = parsed.w ?? parsed.width
        const h = parsed.h ?? parsed.height
        if (typeof w === 'number' && typeof h === 'number') {
          panel_size_by_ws[wsKey] = { w: Math.round(w), h: Math.round(h) }
        }
      }
    }
  } catch {
    /* ignore */
  }
  return { panel_pos_by_ws, panel_size_by_ws }
}

function readSidebarGroups(): Record<string, string> {
  const groups: Record<string, string> = {}
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (!key?.startsWith(SIDEBAR_GROUP_PREFIX)) continue
      const id = key.slice(SIDEBAR_GROUP_PREFIX.length)
      if (!id) continue
      groups[id] = localStorage.getItem(key) ?? '1'
    }
  } catch {
    /* ignore */
  }
  return groups
}


function readAdminOrgFromLocal(): AdminOrgState {
  const defaults = defaultUiStateV1().admin_org
  try {
    const raw = localStorage.getItem(ADMIN_ORG_KEY)
    if (!raw) return defaults
    const parsed = JSON.parse(raw) as Partial<AdminOrgState>
    return {
      active_tab: parsed.active_tab === 'groups' ? 'groups' : 'departments',
      selected_department_id:
        typeof parsed.selected_department_id === 'number' ? parsed.selected_department_id : null,
      expanded_department_ids: Array.isArray(parsed.expanded_department_ids)
        ? parsed.expanded_department_ids.filter((id): id is number => typeof id === 'number')
        : [],
    }
  } catch {
    return defaults
  }
}

function readGettingStartedSeen(userId?: number | string): boolean {
  try {
    const raw = localStorage.getItem('filex_getting_started_seen')
    if (!raw) return false
    if (raw === 'true') return true
    const parsed = JSON.parse(raw) as Record<string, string>
    if (userId != null && parsed && typeof parsed === 'object') {
      return parsed[String(userId)] === '1'
    }
  } catch {
    /* ignore */
  }
  return false
}

export function readLocalSnapshot(userId?: number | string): UserUiStateV1 {
  const base = defaultUiStateV1()

  try {
    const wsRaw = localStorage.getItem('filex_active_workspace_id')
    if (wsRaw) {
      const n = Number(wsRaw)
      if (Number.isFinite(n)) base.active_workspace_id = n
    }
  } catch {
    /* ignore */
  }

  base.getting_started_seen = readGettingStartedSeen(userId)

  base.admin_org = readAdminOrgFromLocal()

  const selectionRaw = readJsonRecord<unknown>('filex_folder_selection_by_workspace')
  const expandedRaw = readJsonRecord<number[]>('filex_folder_expanded_by_workspace')
  const visibleRaw = readJsonRecord<boolean>('filex_folder_panel_visible_by_workspace')
  const panelMaps = readPanelMaps()

  const selection_by_ws: Record<string, FolderSelection> = {}
  for (const [k, v] of Object.entries(selectionRaw)) {
    selection_by_ws[k] = parseSelection(v)
  }
  base.folders = {
    selection_by_ws,
    expanded_by_ws: { ...expandedRaw },
    panel_visible_by_ws: { ...visibleRaw },
    panel_pos_by_ws: panelMaps.panel_pos_by_ws,
    panel_size_by_ws: panelMaps.panel_size_by_ws,
  }

  try {
    const collapsed = localStorage.getItem('filex_sidebar_collapsed')
    if (collapsed != null) base.sidebar.collapsed = collapsed === '1'
  } catch {
    /* ignore */
  }
  base.sidebar.groups = readSidebarGroups()

  try {
    const theme = localStorage.getItem('filex_theme')
    if (theme === 'light' || theme === 'dark' || theme === 'system') base.theme.mode = theme
    const accent = localStorage.getItem('filex_accent')
    if (accent === 'blue') base.theme.accent = 'blue'
  } catch {
    /* ignore */
  }

  try {
    const locale = localStorage.getItem('filex_locale')
    if (locale === 'zh-CN' || locale === 'en') base.locale = locale
  } catch {
    /* ignore */
  }

  try {
    const authMethod = localStorage.getItem('filex_auth_method')
    if (authMethod === 'wechat' || authMethod === 'password') base.login.auth_method = authMethod
    base.login.remember_me = localStorage.getItem('filex_remember_me') !== '0'
  } catch {
    /* ignore */
  }

  try {
    base.kb_eval.cross_workspace = localStorage.getItem('filex_kb_search_cross_workspace') === '1'
    base.kb_eval.filename_boost = localStorage.getItem('filex_kb_eval_filename_boost') !== '0'
    base.kb_eval.modality_boost = localStorage.getItem('filex_kb_eval_modality_boost') === '1'
    const hybrid = localStorage.getItem('filex_kb_eval_hybrid')
    base.kb_eval.hybrid = hybrid == null ? null : hybrid === '1'
    base.kb_eval.query_expansion = localStorage.getItem('filex_kb_eval_query_expansion') === '1'
    const ev = localStorage.getItem('filex_kb_eval_evidence_mode')
    if (ev === 'chunk' || ev === 'monte_carlo') base.kb_eval.evidence_mode = ev
  } catch {
    /* ignore */
  }

  try {
    const posRaw = localStorage.getItem('filex_mq_pet_pos')
    if (posRaw) {
      const parsed = JSON.parse(posRaw) as { x?: number; y?: number }
      if (typeof parsed?.x === 'number' && typeof parsed?.y === 'number') {
        base.mq_pet.pos = { x: Math.round(parsed.x), y: Math.round(parsed.y) }
      }
    }
  } catch {
    /* ignore */
  }

  try {
    const posRaw = localStorage.getItem('filex_kb_toolbar_pos')
    if (posRaw) {
      const parsed = JSON.parse(posRaw) as { x?: number; y?: number }
      if (typeof parsed?.x === 'number' && typeof parsed?.y === 'number') {
        base.kb_toolbar.pos = { x: Math.round(parsed.x), y: Math.round(parsed.y) }
      }
    }
    base.kb_toolbar.collapsed = localStorage.getItem('filex_kb_toolbar_collapsed') === '1'
  } catch {
    /* ignore */
  }

  return base
}

export function hasMeaningfulLocalUiState(snapshot: UserUiStateV1): boolean {
  if (snapshot.active_workspace_id != null) return true
  if (snapshot.getting_started_seen) return true
  const f = snapshot.folders
  if (Object.keys(f.selection_by_ws).length) return true
  if (Object.keys(f.expanded_by_ws).length) return true
  if (Object.keys(f.panel_visible_by_ws).length) return true
  if (Object.keys(f.panel_pos_by_ws).length) return true
  if (Object.keys(f.panel_size_by_ws).length) return true
  if (snapshot.sidebar.collapsed) return true
  if (Object.keys(snapshot.sidebar.groups).length) return true
  if (snapshot.theme.mode !== 'system') return true
  if (snapshot.locale !== 'zh-CN') return true
  if (snapshot.login.auth_method !== 'password') return true
  if (!snapshot.login.remember_me) return true
  if (snapshot.kb_eval.cross_workspace) return true
  if (!snapshot.kb_eval.filename_boost) return true
  if (snapshot.kb_eval.modality_boost) return true
  if (snapshot.kb_eval.hybrid != null) return true
  if (snapshot.kb_eval.query_expansion) return true
  if (snapshot.kb_eval.evidence_mode !== 'chunk') return true
  if (snapshot.mq_pet.pos) return true
  if (snapshot.kb_toolbar.pos) return true
  if (snapshot.kb_toolbar.collapsed) return true
  const ao = snapshot.admin_org
  const def = defaultUiStateV1().admin_org
  if (ao.active_tab !== def.active_tab) return true
  if (ao.selected_department_id != null) return true
  if (ao.expanded_department_ids.length) return true
  return false
}

export function applyUiStateToLocal(state: UserUiStateV1): void {
  try {
    if (state.active_workspace_id != null) {
      localStorage.setItem('filex_active_workspace_id', String(state.active_workspace_id))
    } else {
      localStorage.removeItem('filex_active_workspace_id')
    }
  } catch {
    /* ignore */
  }

  try {
    localStorage.setItem('filex_getting_started_seen', state.getting_started_seen ? 'true' : 'false')
  } catch {
    /* ignore */
  }

  writeJsonRecord('filex_folder_selection_by_workspace', state.folders.selection_by_ws as Record<string, unknown>)
  writeJsonRecord('filex_folder_expanded_by_workspace', state.folders.expanded_by_ws as Record<string, unknown>)
  writeJsonRecord('filex_folder_panel_visible_by_workspace', state.folders.panel_visible_by_ws as Record<string, unknown>)

  try {
    const existing = readPanelMaps()
    const panel_pos_by_ws = { ...existing.panel_pos_by_ws, ...state.folders.panel_pos_by_ws }
    const panel_size_by_ws = { ...existing.panel_size_by_ws, ...state.folders.panel_size_by_ws }

    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i)
      if (key?.startsWith(PANEL_POS_PREFIX) || key?.startsWith(PANEL_SIZE_PREFIX)) {
        localStorage.removeItem(key)
      }
    }
    for (const [wsKey, pos] of Object.entries(panel_pos_by_ws)) {
      localStorage.setItem(`${PANEL_POS_PREFIX}${wsKey}`, JSON.stringify(pos))
    }
    for (const [wsKey, size] of Object.entries(panel_size_by_ws)) {
      localStorage.setItem(`${PANEL_SIZE_PREFIX}${wsKey}`, JSON.stringify({ width: size.w, height: size.h }))
    }
  } catch {
    /* ignore */
  }

  try {
    localStorage.setItem('filex_sidebar_collapsed', state.sidebar.collapsed ? '1' : '0')
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i)
      if (key?.startsWith(SIDEBAR_GROUP_PREFIX)) localStorage.removeItem(key)
    }
    for (const [id, val] of Object.entries(state.sidebar.groups)) {
      localStorage.setItem(`${SIDEBAR_GROUP_PREFIX}${id}`, val)
    }
  } catch {
    /* ignore */
  }

  try {
    localStorage.setItem('filex_theme', state.theme.mode)
    localStorage.setItem('filex_accent', state.theme.accent)
    localStorage.setItem('filex_locale', state.locale)
    localStorage.setItem('filex_auth_method', state.login.auth_method)
    localStorage.setItem('filex_remember_me', state.login.remember_me ? '1' : '0')
  } catch {
    /* ignore */
  }

  try {
    localStorage.setItem('filex_kb_search_cross_workspace', state.kb_eval.cross_workspace ? '1' : '0')
    localStorage.setItem('filex_kb_eval_filename_boost', state.kb_eval.filename_boost ? '1' : '0')
    localStorage.setItem('filex_kb_eval_modality_boost', state.kb_eval.modality_boost ? '1' : '0')
    if (state.kb_eval.hybrid == null) localStorage.removeItem('filex_kb_eval_hybrid')
    else localStorage.setItem('filex_kb_eval_hybrid', state.kb_eval.hybrid ? '1' : '0')
    localStorage.setItem('filex_kb_eval_query_expansion', state.kb_eval.query_expansion ? '1' : '0')
    localStorage.setItem('filex_kb_eval_evidence_mode', state.kb_eval.evidence_mode)
  } catch {
    /* ignore */
  }

  try {
    if (state.mq_pet.pos) localStorage.setItem('filex_mq_pet_pos', JSON.stringify(state.mq_pet.pos))
    else localStorage.removeItem('filex_mq_pet_pos')
  } catch {
    /* ignore */
  }

  try {
    if (state.kb_toolbar.pos) {
      localStorage.setItem('filex_kb_toolbar_pos', JSON.stringify(state.kb_toolbar.pos))
    } else {
      localStorage.removeItem('filex_kb_toolbar_pos')
    }
    localStorage.setItem('filex_kb_toolbar_collapsed', state.kb_toolbar.collapsed ? '1' : '0')
  } catch {
    /* ignore */
  }

  try {
    localStorage.setItem(ADMIN_ORG_KEY, JSON.stringify(state.admin_org))
  } catch {
    /* ignore */
  }

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(UI_STATE_LOCAL_APPLIED_EVENT))
  }
}

export function readFoldersFromLocal(): FoldersState {
  return readLocalSnapshot().folders
}

export function clearLegacyLocalKeys(): void {
  for (const key of LEGACY_KEYS) {
    try {
      localStorage.removeItem(key)
    } catch {
      /* ignore */
    }
  }
  // panel_pos/size 与 sidebar group 键仍是活跃本地缓存，勿在此删除（039 同步后由 applyUiStateToLocal 维护）
}
