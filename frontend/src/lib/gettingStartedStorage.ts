import type { ApiKeyGateState } from '@/lib/apiKeyOnboardingGate'
import { getCachedUiState, markGettingStartedSeenAndSync } from '@/lib/uiStateSync'

const STORAGE_KEY = 'filex_getting_started_seen'
const AUTO_OPEN_CACHE_PREFIX = 'filex:gettingStartedAuto:'

export type GettingStartedAutoOpenState = 'pending' | 'open' | 'closed'

function autoOpenCacheKey(userId: number | string): string {
  return `${AUTO_OPEN_CACHE_PREFIX}${userId}`
}

function readLocalGettingStartedSeen(userId: number | string): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return false
    if (raw === 'true') return true
    const parsed = JSON.parse(raw) as Record<string, string>
    if (parsed && typeof parsed === 'object') return parsed[String(userId)] === '1'
  } catch {
    /* ignore */
  }
  return false
}

/** 同会话内缓存自动引导决策，避免已读用户每次登录闪现新手引导 */
export function readGettingStartedAutoOpenCache(
  userId: number | string,
): 'open' | 'closed' | null {
  try {
    const raw = sessionStorage.getItem(autoOpenCacheKey(userId))
    if (raw === 'open' || raw === 'closed') return raw
  } catch {
    /* ignore */
  }
  return null
}

export function writeGettingStartedAutoOpenCache(
  userId: number | string,
  state: 'open' | 'closed',
): void {
  try {
    sessionStorage.setItem(autoOpenCacheKey(userId), state)
  } catch {
    /* ignore */
  }
}

export function hasSeenGettingStarted(userId: number | string): boolean {
  if (readLocalGettingStartedSeen(userId)) return true
  const cached = getCachedUiState()
  if (cached != null) return cached.getting_started_seen
  return false
}

export function resolveGettingStartedAutoOpenState(
  userId: number | undefined,
  apiKeyGate: ApiKeyGateState,
): GettingStartedAutoOpenState {
  if (!userId) return 'pending'
  if (apiKeyGate !== 'ok') return 'pending'

  if (hasSeenGettingStarted(userId)) {
    writeGettingStartedAutoOpenCache(userId, 'closed')
    return 'closed'
  }

  const sessionCached = readGettingStartedAutoOpenCache(userId)
  if (sessionCached === 'closed') return 'closed'

  return 'open'
}

export function markGettingStartedSeen(userId: number | string): void {
  writeGettingStartedAutoOpenCache(userId, 'closed')
  markGettingStartedSeenAndSync()
}
