import type { ApiKeyItem } from '@/api/apiKeys'
import { hasActiveApiKey } from '@/lib/apiKeyOnboarding'

export type ApiKeyGateState = 'pending' | 'blocked' | 'ok' | 'error'

export type ApiKeyGateCacheState = 'ok' | 'blocked'

const API_KEY_GATE_CACHE_PREFIX = 'filex:apiKeyGate:'

function apiKeyGateCacheKey(userId: number): string {
  return `${API_KEY_GATE_CACHE_PREFIX}${userId}`
}

/** 同会话内缓存 gate 结果，避免已有密钥用户每次进主界面闪现检查弹窗 */
export function readApiKeyGateCache(userId: number): ApiKeyGateCacheState | null {
  try {
    const raw = sessionStorage.getItem(apiKeyGateCacheKey(userId))
    if (raw === 'ok' || raw === 'blocked') return raw
  } catch {
    /* ignore */
  }
  return null
}

export function writeApiKeyGateCache(userId: number, state: ApiKeyGateCacheState): void {
  try {
    sessionStorage.setItem(apiKeyGateCacheKey(userId), state)
  } catch {
    /* ignore */
  }
}

export function initialApiKeyGateState(userId: number | undefined): ApiKeyGateState {
  if (!userId) return 'pending'
  const cached = readApiKeyGateCache(userId)
  if (cached === 'ok') return 'ok'
  if (cached === 'blocked') return 'blocked'
  return 'pending'
}

/** 阻断弹窗统一 guard，SC-075-002 */
export const API_KEY_ONBOARDING_MODAL_GUARD = {
  closable: false,
  maskClosable: false,
  keyboard: false,
} as const

export function resolveApiKeyGateFromList(keys: ApiKeyItem[]): 'ok' | 'blocked' {
  return hasActiveApiKey(keys) ? 'ok' : 'blocked'
}

export async function loadApiKeyGateState(
  fetchKeys: () => Promise<ApiKeyItem[]>,
): Promise<'ok' | 'blocked' | 'error'> {
  try {
    const keys = await fetchKeys()
    return resolveApiKeyGateFromList(keys)
  } catch {
    return 'error'
  }
}

/** SC-075-004：gate 非 ok 时不自动打开新手引导 */
export function shouldAutoOpenGettingStarted(
  apiKeyGate: ApiKeyGateState,
  hasSeen: boolean,
): boolean {
  return apiKeyGate === 'ok' && !hasSeen
}
