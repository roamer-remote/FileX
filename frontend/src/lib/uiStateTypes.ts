/** 039 user_ui_state v1 — 对齐 backend UserUiStateV1 */

export type FolderSelection = 'all' | 'uncategorized' | number

export type PanelPos = { x: number; y: number }
export type PanelSize = { w: number; h: number }
export type MqPetPos = { x: number; y: number }

export type FoldersState = {
  selection_by_ws: Record<string, FolderSelection>
  expanded_by_ws: Record<string, number[]>
  panel_visible_by_ws: Record<string, boolean>
  panel_pos_by_ws: Record<string, PanelPos>
  panel_size_by_ws: Record<string, PanelSize>
}

export type SidebarState = {
  collapsed: boolean
  groups: Record<string, string>
}

export type ThemeState = {
  mode: 'light' | 'dark' | 'system'
  accent: 'blue'
}

export type LoginPrefs = {
  auth_method: 'password' | 'wechat'
  remember_me: boolean
}

export type KbEvalState = {
  cross_workspace: boolean
  filename_boost: boolean
  modality_boost: boolean
  hybrid: boolean | null
  query_expansion: boolean
  evidence_mode: 'chunk' | 'monte_carlo'
}

export type MqPetState = {
  pos: MqPetPos | null
}

export type KbToolbarState = {
  pos: MqPetPos | null
  collapsed: boolean
}

export type AdminOrgTab = 'departments' | 'groups'

export type AdminOrgState = {
  active_tab: AdminOrgTab
  selected_department_id: number | null
  expanded_department_ids: number[]
}

export type KbIndexMainTab = 'preview' | 'okf'
export type KbIndexPreviewSubTab = 'auto' | 'wikiPages' | 'wiki' | 'linkGraph'

export type KbIndexState = {
  active_tab: KbIndexMainTab
  preview_sub_tab: KbIndexPreviewSubTab
}

export type UserUiStateV1 = {
  v: 1
  active_workspace_id: number | null
  getting_started_seen: boolean
  folders: FoldersState
  sidebar: SidebarState
  theme: ThemeState
  locale: 'zh-CN' | 'en'
  login: LoginPrefs
  kb_eval: KbEvalState
  mq_pet: MqPetState
  kb_toolbar: KbToolbarState
  admin_org: AdminOrgState
  kb_index: KbIndexState
}

export function defaultUiStateV1(): UserUiStateV1 {
  return {
    v: 1,
    active_workspace_id: null,
    getting_started_seen: false,
    folders: {
      selection_by_ws: {},
      expanded_by_ws: {},
      panel_visible_by_ws: {},
      panel_pos_by_ws: {},
      panel_size_by_ws: {},
    },
    sidebar: { collapsed: false, groups: {} },
    theme: { mode: 'system', accent: 'blue' },
    locale: 'zh-CN',
    login: { auth_method: 'password', remember_me: true },
    kb_eval: {
      cross_workspace: false,
      filename_boost: true,
      modality_boost: false,
      hybrid: null,
      query_expansion: false,
      evidence_mode: 'chunk',
    },
    mq_pet: { pos: null },
    kb_toolbar: { pos: null, collapsed: false },
    admin_org: {
      active_tab: 'departments',
      selected_department_id: null,
      expanded_department_ids: [],
    },
    kb_index: { active_tab: 'preview', preview_sub_tab: 'auto' },
  }
}

export type UiStateResponse = {
  state: UserUiStateV1
  updated_at: string | null
}

export type UiStatePatch = Partial<Omit<UserUiStateV1, 'v'>> & { v?: 1 }
