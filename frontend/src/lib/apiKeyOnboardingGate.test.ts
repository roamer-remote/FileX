import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ApiKeyItem } from '@/api/apiKeys'
import {
  API_KEY_ONBOARDING_MODAL_GUARD,
  initialApiKeyGateState,
  loadApiKeyGateState,
  readApiKeyGateCache,
  resolveApiKeyGateFromList,
  shouldAutoOpenGettingStarted,
  writeApiKeyGateCache,
} from './apiKeyOnboardingGate'

function key(partial: Partial<ApiKeyItem> & Pick<ApiKeyItem, 'id'>): ApiKeyItem {
  return {
    name: 'test',
    prefix: 'fb_abcd',
    created_at: '2026-01-01T00:00:00+08:00',
    last_used_at: null,
    is_active: true,
    can_reveal: true,
    ...partial,
  }
}

describe('resolveApiKeyGateFromList', () => {
  it('returns blocked for empty list', () => {
    expect(resolveApiKeyGateFromList([])).toBe('blocked')
  })

  it('returns blocked when all keys inactive', () => {
    expect(resolveApiKeyGateFromList([key({ id: 1, is_active: false })])).toBe('blocked')
  })

  it('returns ok when at least one key is active', () => {
    expect(resolveApiKeyGateFromList([key({ id: 1, is_active: true })])).toBe('ok')
  })
})

describe('loadApiKeyGateState', () => {
  it('returns error when fetch fails', async () => {
    await expect(
      loadApiKeyGateState(async () => {
        throw new Error('network')
      }),
    ).resolves.toBe('error')
  })

  it('returns blocked then ok after create refresh sequence', async () => {
    let call = 0
    const fetchKeys = vi.fn(async () => {
      call += 1
      return call === 1 ? [] : [key({ id: 2, is_active: true })]
    })

    expect(await loadApiKeyGateState(fetchKeys)).toBe('blocked')
    expect(await loadApiKeyGateState(fetchKeys)).toBe('ok')
    expect(fetchKeys).toHaveBeenCalledTimes(2)
  })

  it('returns ok when list already has active key', async () => {
    await expect(
      loadApiKeyGateState(async () => [key({ id: 1, is_active: true })]),
    ).resolves.toBe('ok')
  })
})

describe('shouldAutoOpenGettingStarted', () => {
  it('does not open while gate is pending', () => {
    expect(shouldAutoOpenGettingStarted('pending', false)).toBe(false)
  })

  it('does not open while gate is blocked', () => {
    expect(shouldAutoOpenGettingStarted('blocked', false)).toBe(false)
  })

  it('does not open while gate is error', () => {
    expect(shouldAutoOpenGettingStarted('error', false)).toBe(false)
  })

  it('opens only when gate is ok and user has not seen guide', () => {
    expect(shouldAutoOpenGettingStarted('ok', false)).toBe(true)
    expect(shouldAutoOpenGettingStarted('ok', true)).toBe(false)
  })
})

describe('API_KEY_ONBOARDING_MODAL_GUARD', () => {
  it('blocks dismiss via close button, mask, and keyboard', () => {
    expect(API_KEY_ONBOARDING_MODAL_GUARD).toEqual({
      closable: false,
      maskClosable: false,
      keyboard: false,
    })
  })
})

describe('apiKeyGate session cache', () => {
  const userId = 42

  beforeEach(() => {
    sessionStorage.clear()
  })

  it('initialApiKeyGateState uses cached ok without pending', () => {
    writeApiKeyGateCache(userId, 'ok')
    expect(initialApiKeyGateState(userId)).toBe('ok')
  })

  it('initialApiKeyGateState uses cached blocked', () => {
    writeApiKeyGateCache(userId, 'blocked')
    expect(initialApiKeyGateState(userId)).toBe('blocked')
  })

  it('initialApiKeyGateState falls back to pending when no cache', () => {
    expect(initialApiKeyGateState(userId)).toBe('pending')
    expect(initialApiKeyGateState(undefined)).toBe('pending')
  })

  it('readApiKeyGateCache ignores invalid values', () => {
    sessionStorage.setItem('filex:apiKeyGate:42', 'weird')
    expect(readApiKeyGateCache(userId)).toBeNull()
  })
})
