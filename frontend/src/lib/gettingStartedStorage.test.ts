import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { defaultUiStateV1, type UserUiStateV1 } from '@/lib/uiStateTypes'

function createMemoryStorage() {
  const map = new Map<string, string>()
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => {
      map.set(key, value)
    },
    removeItem: (key: string) => {
      map.delete(key)
    },
    clear: () => {
      map.clear()
    },
  }
}

let cachedUiState: UserUiStateV1 | null = null

vi.mock('@/lib/uiStateSync', () => ({
  getCachedUiState: () => cachedUiState,
  markGettingStartedSeenAndSync: vi.fn(),
}))

import {
  hasSeenGettingStarted,
  readGettingStartedAutoOpenCache,
  resolveGettingStartedAutoOpenState,
  writeGettingStartedAutoOpenCache,
} from './gettingStartedStorage'

beforeAll(() => {
  vi.stubGlobal('localStorage', createMemoryStorage())
  vi.stubGlobal('sessionStorage', createMemoryStorage())
})

describe('hasSeenGettingStarted', () => {
  beforeEach(() => {
    cachedUiState = defaultUiStateV1()
    localStorage.clear()
    sessionStorage.clear()
  })

  it('prefers localStorage true over cached false', () => {
    localStorage.setItem('filex_getting_started_seen', 'true')
    cachedUiState = { ...defaultUiStateV1(), getting_started_seen: false }
    expect(hasSeenGettingStarted(7)).toBe(true)
  })

  it('falls back to cached ui state when localStorage is false', () => {
    localStorage.setItem('filex_getting_started_seen', 'false')
    cachedUiState = { ...defaultUiStateV1(), getting_started_seen: true }
    expect(hasSeenGettingStarted(7)).toBe(true)
  })
})

describe('resolveGettingStartedAutoOpenState', () => {
  const userId = 9

  beforeEach(() => {
    cachedUiState = { ...defaultUiStateV1(), getting_started_seen: false }
    localStorage.clear()
    sessionStorage.clear()
  })

  it('stays pending while api key gate is not ok', () => {
    expect(resolveGettingStartedAutoOpenState(userId, 'pending')).toBe('pending')
    expect(resolveGettingStartedAutoOpenState(userId, 'blocked')).toBe('pending')
  })

  it('returns closed for seen users without opening flash', () => {
    localStorage.setItem('filex_getting_started_seen', 'true')
    expect(resolveGettingStartedAutoOpenState(userId, 'ok')).toBe('closed')
    expect(readGettingStartedAutoOpenCache(userId)).toBe('closed')
  })

  it('returns open for first-time users once api key gate is ok', () => {
    expect(resolveGettingStartedAutoOpenState(userId, 'ok')).toBe('open')
  })

  it('uses session cache closed to skip auto open in same session', () => {
    writeGettingStartedAutoOpenCache(userId, 'closed')
    expect(resolveGettingStartedAutoOpenState(userId, 'ok')).toBe('closed')
  })
})
