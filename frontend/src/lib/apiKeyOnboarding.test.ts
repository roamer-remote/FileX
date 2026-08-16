import { describe, expect, it } from 'vitest'
import type { ApiKeyItem } from '@/api/apiKeys'
import { hasActiveApiKey } from './apiKeyOnboarding'

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

describe('hasActiveApiKey', () => {
  it('returns false for empty list', () => {
    expect(hasActiveApiKey([])).toBe(false)
  })

  it('returns false when all keys are inactive', () => {
    expect(hasActiveApiKey([key({ id: 1, is_active: false })])).toBe(false)
  })

  it('returns true when at least one key is active', () => {
    expect(
      hasActiveApiKey([
        key({ id: 1, is_active: false }),
        key({ id: 2, is_active: true }),
      ]),
    ).toBe(true)
  })
})
