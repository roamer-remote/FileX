import { describe, expect, it } from 'vitest'
import { normalizeBuildVersion } from './buildVersion'

describe('normalizeBuildVersion', () => {
  it('accepts yyyy-mm-dd-hh-mm-ss plus 7-char hex sha', () => {
    expect(normalizeBuildVersion('2026-06-18-14-30-00-a1b2c3d')).toBe('2026-06-18-14-30-00-a1b2c3d')
  })

  it('trims surrounding whitespace', () => {
    expect(normalizeBuildVersion('  2026-06-18-14-30-00-a1b2c3d  ')).toBe('2026-06-18-14-30-00-a1b2c3d')
  })

  it('rejects 8-char sha', () => {
    expect(normalizeBuildVersion('2026-06-18-14-30-00-deadbeef')).toBe('')
  })

  it('rejects malformed values', () => {
    expect(normalizeBuildVersion('bad')).toBe('')
    expect(normalizeBuildVersion(undefined)).toBe('')
    expect(normalizeBuildVersion('')).toBe('')
  })
})
