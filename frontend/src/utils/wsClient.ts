import { clearAuthStorage, isAuthEntryPath } from '@/api/index'

export const WS_CLOSE_UNAUTHORIZED = 4401
export const WS_CLOSE_FORBIDDEN = 4403

export function wsBaseUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}`
}

export function handleWebSocketClose(code: number): 'stop' | 'retry' | 'logout' {
  if (code === WS_CLOSE_UNAUTHORIZED) {
    clearAuthStorage()
    if (!isAuthEntryPath()) {
      window.location.href = '/login'
    }
    return 'logout'
  }
  if (code === WS_CLOSE_FORBIDDEN) return 'stop'
  return 'retry'
}
