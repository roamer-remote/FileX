import { describe, expect, it } from 'vitest'
import type { TFunction } from 'i18next'
import { buildForceReindexConfirmContent } from './kbForceReindexConfirm'

describe('buildForceReindexConfirmContent', () => {
  const t = ((key: string, opts?: { count?: number }) => {
    if (key === 'kbChunks.forceReindexConfirmContent') return 'BASE'
    if (key === 'kbChunks.forceReindexLargeDocHint') return `HINT:${opts?.count ?? 0}`
    return key
  }) as TFunction

  it('returns base content without large doc hint', () => {
    expect(buildForceReindexConfirmContent(t)).toBe('BASE')
  })

  it('appends large doc hint when requested', () => {
    expect(buildForceReindexConfirmContent(t, { largeDocHint: true, chunkCount: 2470 })).toBe(
      'BASE\n\nHINT:2470',
    )
  })
})
