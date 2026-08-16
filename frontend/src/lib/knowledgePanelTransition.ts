/** 资料库大厅 → 功能面板：随机切换动效（session 内记住当前一次，便于开闭配对） */

export const KB_PANEL_TRANSITIONS = [
  'slide-up',
  'slide-down',
  'slide-right',
  'slide-left',
  'zoom-in',
  'zoom-out',
  'fade-rise',
  'blur-fade',
  'rotate-in',
  'bounce-up',
] as const

export type KbPanelTransitionId = (typeof KB_PANEL_TRANSITIONS)[number]

const SESSION_KEY = 'filex_kb_panel_transition_active'

function isTransitionId(value: string): value is KbPanelTransitionId {
  return (KB_PANEL_TRANSITIONS as readonly string[]).includes(value)
}

/** 随机选取一种面板进入动效，并写入 sessionStorage */
export function pickKbPanelTransition(): KbPanelTransitionId {
  const index = Math.floor(Math.random() * KB_PANEL_TRANSITIONS.length)
  const picked = KB_PANEL_TRANSITIONS[index]
  try {
    sessionStorage.setItem(SESSION_KEY, picked)
  } catch {
    /* private mode / quota */
  }
  return picked
}

export function readActiveKbPanelTransition(): KbPanelTransitionId | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (raw && isTransitionId(raw)) return raw
  } catch {
    /* ignore */
  }
  return null
}

export function clearActiveKbPanelTransition(): void {
  try {
    sessionStorage.removeItem(SESSION_KEY)
  } catch {
    /* ignore */
  }
}
