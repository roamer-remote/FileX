import { getUiState, migrateUiState, putUiState } from '@/api/uiState'
import {
  applyUiStateToLocal,
  clearLegacyLocalKeys,
  hasMeaningfulLocalUiState,
  readFoldersFromLocal,
  readLocalSnapshot,
} from '@/lib/uiStateLocalSnapshot'
import type { AdminOrgState, KbIndexState, UiStatePatch, UserUiStateV1 } from '@/lib/uiStateTypes'
import { defaultUiStateV1 } from '@/lib/uiStateTypes'
import { hydrateFolderSelection, useFoldersStore } from '@/stores/foldersStore'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import i18n from '@/i18n'

let cachedState: UserUiStateV1 | null = null
let pendingPatch: Record<string, unknown> = {}
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let flushInFlight = false

export function getCachedUiState(): UserUiStateV1 | null {
  return cachedState
}

export function setCachedUiState(state: UserUiStateV1): void {
  cachedState = state
}

/** 登出或新会话 hydrate 前清空内存态，避免跨用户 pendingPatch / cachedState 泄漏。 */
export function resetUiStateSync(): void {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
  cachedState = null
  pendingPatch = {}
}

function panelMapsDiffer(a: UserUiStateV1, b: UserUiStateV1): boolean {
  const fa = a.folders
  const fb = b.folders
  return (
    JSON.stringify(fa.panel_pos_by_ws) !== JSON.stringify(fb.panel_pos_by_ws) ||
    JSON.stringify(fa.panel_size_by_ws) !== JSON.stringify(fb.panel_size_by_ws)
  )
}

/** 服务端缺少的浮窗位置/尺寸用 localStorage 补全（避免 PUT 失败或 migrate 后本地被空状态覆盖） */
function mergeLocalPanelMapsIntoState(state: UserUiStateV1): UserUiStateV1 {
  const localFolders = readLocalSnapshot().folders
  const panel_pos_by_ws = { ...state.folders.panel_pos_by_ws }
  const panel_size_by_ws = { ...state.folders.panel_size_by_ws }
  let changed = false

  for (const [k, v] of Object.entries(localFolders.panel_pos_by_ws)) {
    if (!(k in panel_pos_by_ws)) {
      panel_pos_by_ws[k] = v
      changed = true
    }
  }
  for (const [k, v] of Object.entries(localFolders.panel_size_by_ws)) {
    if (!(k in panel_size_by_ws)) {
      panel_size_by_ws[k] = v
      changed = true
    }
  }

  if (!changed) return state
  return {
    ...state,
    folders: {
      ...state.folders,
      panel_pos_by_ws,
      panel_size_by_ws,
    },
  }
}

/** 登录页已选方式优先于服务端默认 password（bootstrap 前 localStorage 已有值时保留） */
function mergeLocalLoginPrefsIntoState(state: UserUiStateV1): UserUiStateV1 {
  try {
    const am = localStorage.getItem('filex_auth_method')
    const rm = localStorage.getItem('filex_remember_me')
    if (am !== 'wechat' && am !== 'password' && rm === null) return state
    return {
      ...state,
      login: {
        ...state.login,
        ...(am === 'wechat' || am === 'password' ? { auth_method: am } : {}),
        ...(rm !== null ? { remember_me: rm !== '0' } : {}),
      },
    }
  } catch {
    return state
  }
}

function deepMergeClient(base: Record<string, unknown>, patch: Record<string, unknown>): Record<string, unknown> {
  const result = { ...base }
  for (const [key, value] of Object.entries(patch)) {
    const existing = result[key]
    if (existing && typeof existing === 'object' && !Array.isArray(existing) && value && typeof value === 'object' && !Array.isArray(value)) {
      result[key] = deepMergeClient(existing as Record<string, unknown>, value as Record<string, unknown>)
    } else {
      result[key] = value
    }
  }
  return result
}

export async function flushUiStatePatch(retry = false): Promise<void> {
  if (flushInFlight) return
  const patch = pendingPatch
  if (!Object.keys(patch).length) return
  pendingPatch = {}
  flushInFlight = true
  try {
    const res = await putUiState(patch)
    cachedState = mergeLocalPanelMapsIntoState(res.data.state)
  } catch {
    if (!retry) {
      pendingPatch = deepMergeClient(pendingPatch, patch)
      window.setTimeout(() => {
        void flushUiStatePatch(true)
      }, 2000)
    }
  } finally {
    flushInFlight = false
  }
}

function mergeCachedState(state: UserUiStateV1, partial: UiStatePatch): UserUiStateV1 {
  return {
    ...state,
    ...partial,
    folders: partial.folders ?? state.folders,
    sidebar: partial.sidebar ? { ...state.sidebar, ...partial.sidebar } : state.sidebar,
    theme: partial.theme ? { ...state.theme, ...partial.theme } : state.theme,
    login: partial.login ? { ...state.login, ...partial.login } : state.login,
    kb_eval: partial.kb_eval ? { ...state.kb_eval, ...partial.kb_eval } : state.kb_eval,
    mq_pet: partial.mq_pet ? { ...state.mq_pet, ...partial.mq_pet } : state.mq_pet,
    kb_toolbar: partial.kb_toolbar
      ? { ...state.kb_toolbar, ...partial.kb_toolbar }
      : state.kb_toolbar,
    admin_org: partial.admin_org ? { ...state.admin_org, ...partial.admin_org } : state.admin_org,
    kb_index: partial.kb_index ? { ...state.kb_index, ...partial.kb_index } : state.kb_index,
  }
}

export function patchUiState(partial: UiStatePatch): void {
  if (cachedState) {
    cachedState = mergeCachedState(cachedState, partial)
  }
  pendingPatch = deepMergeClient(pendingPatch, partial as Record<string, unknown>)
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    void flushUiStatePatch()
  }, 500)
}

export function patchFoldersUiState(): void {
  patchUiState({ folders: readFoldersFromLocal() })
}

export function applyUiStateToStores(state: UserUiStateV1): void {
  setCachedUiState(state)
  useThemeStore.getState().hydrateFromStorage()
  if (state.locale && i18n.language !== state.locale) {
    void i18n.changeLanguage(state.locale)
  }
}

export async function hydrateUiStateFromServer(): Promise<UserUiStateV1> {
  resetUiStateSync()
  const userId = useAuthStore.getState().user?.id
  const res = await getUiState()
  if (res.data.updated_at == null) {
    const snapshot = readLocalSnapshot(userId)
    if (hasMeaningfulLocalUiState(snapshot)) {
      const migrated = await migrateUiState(snapshot)
      clearLegacyLocalKeys()
      const merged = mergeLocalLoginPrefsIntoState(migrated.data.state)
      setCachedUiState(merged)
      return merged
    }
    const empty = defaultUiStateV1()
    setCachedUiState(empty)
    return empty
  }
  const merged = mergeLocalLoginPrefsIntoState(res.data.state)
  setCachedUiState(merged)
  return merged
}

export async function bootstrapUiStateAfterAuth(): Promise<void> {
  const state = await hydrateUiStateFromServer()
  const loginMerged = mergeLocalLoginPrefsIntoState(state)
  const merged = mergeLocalPanelMapsIntoState(loginMerged)
  applyUiStateToLocal(merged)
  setCachedUiState(merged)
  applyUiStateToStores(merged)

  if (panelMapsDiffer(merged, loginMerged)) {
    patchFoldersUiState()
    await flushUiStatePatch()
  }

  if (merged.active_workspace_id != null) {
    useWorkspaceStore.setState({ activeWorkspaceId: merged.active_workspace_id })
  }

  await useWorkspaceStore.getState().fetchWorkspaces()
  hydrateFolderSelection()
  void useFoldersStore.getState().fetchFolders()
}

export async function syncLoginPrefsToServer(rememberMe: boolean, authMethod: 'password' | 'wechat'): Promise<void> {
  try {
    localStorage.setItem('filex_auth_method', authMethod)
    localStorage.setItem('filex_remember_me', rememberMe ? '1' : '0')
  } catch {
    /* ignore */
  }
  patchUiState({
    login: { remember_me: rememberMe, auth_method: authMethod },
  })
  await flushUiStatePatch()
  if (cachedState) {
    applyUiStateToLocal(mergeLocalPanelMapsIntoState(cachedState))
  }
}

export function markGettingStartedSeenAndSync(): void {
  try {
    localStorage.setItem('filex_getting_started_seen', 'true')
  } catch {
    /* ignore */
  }
  patchUiState({ getting_started_seen: true })
}


export function patchKbEvalUiState(): void {
  patchUiState({ kb_eval: readLocalSnapshot().kb_eval })
}

export function patchSidebarUiState(): void {
  patchUiState({ sidebar: readLocalSnapshot().sidebar })
}

export function patchThemeUiState(mode: 'light' | 'dark' | 'system'): void {
  patchUiState({ theme: { mode, accent: 'blue' } })
}

export function patchLocaleUiState(locale: 'zh-CN' | 'en'): void {
  patchUiState({ locale })
}

export function patchMqPetUiState(): void {
  patchUiState({ mq_pet: readLocalSnapshot().mq_pet })
}

export function patchKbToolbarUiState(): void {
  patchUiState({ kb_toolbar: readLocalSnapshot().kb_toolbar })
}

export function patchAdminOrgUiState(partial: Partial<AdminOrgState>): void {
  patchUiState({ admin_org: partial } as UiStatePatch)
}

export function patchKbIndexUiState(partial: Partial<KbIndexState>): void {
  patchUiState({ kb_index: partial } as UiStatePatch)
}
