import { describe, expect, it } from 'vitest'
import {
  GOLDEN_FIGURE_CHUNK,
  GOLDEN_FIGURE_META_SUMMARY,
  GOLDEN_TABLE_CHUNK,
  GOLDEN_TABLE_META_SUMMARY,
} from '@/fixtures/kbChunkMultimodalGolden'
import {
  formatMultimodalMetaSummary,
  isMultimodalReadOnlyKind,
  multimodalKindTagColor,
} from './kbChunkMultimodalDisplay'

describe('kbChunkMultimodalDisplay SC-047-009 golden', () => {
  it('figure chunk 为只读多模态', () => {
    expect(isMultimodalReadOnlyKind(GOLDEN_FIGURE_CHUNK.content_kind)).toBe(true)
    expect(multimodalKindTagColor('figure')).toBe('blue')
    expect(
      formatMultimodalMetaSummary(GOLDEN_FIGURE_CHUNK.content_kind, GOLDEN_FIGURE_CHUNK.content_meta ?? null),
    ).toBe(GOLDEN_FIGURE_META_SUMMARY)
  })

  it('table chunk 为只读多模态', () => {
    expect(isMultimodalReadOnlyKind(GOLDEN_TABLE_CHUNK.content_kind)).toBe(true)
    expect(multimodalKindTagColor('table')).toBe('green')
    expect(
      formatMultimodalMetaSummary(GOLDEN_TABLE_CHUNK.content_kind, GOLDEN_TABLE_CHUNK.content_meta ?? null),
    ).toBe(GOLDEN_TABLE_META_SUMMARY)
  })

  it('普通 text chunk 非只读多模态', () => {
    expect(isMultimodalReadOnlyKind('text')).toBe(false)
    expect(isMultimodalReadOnlyKind(null)).toBe(false)
    expect(formatMultimodalMetaSummary('text', null)).toBe('—')
  })

  it('equation 为只读多模态', () => {
    expect(isMultimodalReadOnlyKind('equation')).toBe(true)
    expect(formatMultimodalMetaSummary('equation', { page_idx: 2 })).toBe('p2')
  })
})
