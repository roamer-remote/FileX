import { useCallback, useState } from 'react'

export type MqMonitorTab = 'factory' | 'classic'

const STORAGE_KEY = 'filex_mq_monitor_tab'

function readStoredTab(): MqMonitorTab {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw === 'classic' || raw === 'factory') return raw
  } catch {
    /* ignore */
  }
  return 'factory'
}

export function useMqMonitorTab() {
  const [tab, setTabState] = useState<MqMonitorTab>(() => readStoredTab())

  const setTab = useCallback((next: MqMonitorTab) => {
    setTabState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* ignore */
    }
  }, [])

  return [tab, setTab] as const
}
