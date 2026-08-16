import { describe, expect, it } from 'vitest'
import { normalizeWikiSlug } from '@/utils/wikiSlug'

describe('normalizeWikiSlug', () => {
  it.each([
    ['重要人才', '重要人才'],
    ['CRISPR 基因编辑', 'crispr-基因编辑'],
    ['crispr-gene-editing', 'crispr-gene-editing'],
    ['  VIP  ', 'vip'],
    ['ＣＲＩＳＰＲ', 'crispr'],
    ['重要__人才', '重要-人才'],
    ['', ''],
    ['---', ''],
    ['|invalid|', 'invalid'],
  ])('normalizeWikiSlug(%j) => %j', (raw, expected) => {
    expect(normalizeWikiSlug(raw)).toBe(expected)
  })

  it('truncates to 128 chars', () => {
    expect(normalizeWikiSlug('中'.repeat(200)).length).toBe(128)
  })
})
