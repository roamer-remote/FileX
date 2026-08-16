import { create } from 'zustand'
import { patchThemeUiState } from '@/lib/uiStateSync'

export type ThemePersistMode = 'light' | 'dark' | 'system'

type ThemeState = {
  mode: ThemePersistMode
  systemDark: boolean
  resolvedMode: 'light' | 'dark'
  hydrateFromStorage: () => void
  setMode: (m: ThemePersistMode) => void
}

function computeResolved(mode: ThemePersistMode, systemDark: boolean): 'light' | 'dark' {
  if (mode === 'system') return systemDark ? 'dark' : 'light'
  return mode
}

function applyDom(resolved: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', resolved)
  document.documentElement.classList.toggle('dark', resolved === 'dark')
}

let mediaListener: ((e: MediaQueryListEvent) => void) | null = null

export const useThemeStore = create<ThemeState>((set, get) => ({
  mode: 'system',
  systemDark: typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches,
  resolvedMode: 'light',

  hydrateFromStorage: () => {
    const raw = (localStorage.getItem('filex_theme') as ThemePersistMode | null) || 'system'
    const mode: ThemePersistMode = raw === 'light' || raw === 'dark' || raw === 'system' ? raw : 'system'
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const resolvedMode = computeResolved(mode, systemDark)
    const accent = localStorage.getItem('filex_accent') || 'blue'
    document.documentElement.setAttribute('data-accent', accent)
    applyDom(resolvedMode)
    set({ mode, systemDark, resolvedMode })

    if (!mediaListener) {
      const mq = window.matchMedia('(prefers-color-scheme: dark)')
      mediaListener = (e) => {
        const st = get()
        if (st.mode !== 'system') return
        const r = e.matches ? 'dark' : 'light'
        applyDom(r)
        set({ systemDark: e.matches, resolvedMode: r })
      }
      mq.addEventListener('change', mediaListener)
    }
  },

  setMode: (m) => {
    localStorage.setItem('filex_theme', m)
    patchThemeUiState(m)
    const systemDark = get().systemDark
    const resolvedMode = computeResolved(m, systemDark)
    applyDom(resolvedMode)
    set({ mode: m, resolvedMode })
  },
}))
