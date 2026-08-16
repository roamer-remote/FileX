import { describe, expect, it } from 'vitest'
import type { KbChunkHit } from '@/api/knowledgeBase'
import { dedupeKbHitsByFile } from '@/lib/kbEvalDedupe'

function hit(fileId: number, chunkIndex = 0): KbChunkHit {
  return {
    file_id: fileId,
    chunk_index: chunkIndex,
    original_name: `file-${fileId}.pdf`,
    has_md: true,
    source: 'sidecar_md',
    text: 'sample',
    score: 0.9 - chunkIndex * 0.1,
    char_start: 0,
    char_end: 10,
  }
}

describe('dedupeKbHitsByFile', () => {
  it('removes duplicate file_id and keeps first occurrence order', () => {
    const items = [hit(1), hit(2), hit(1, 1), hit(3), hit(2, 2)]
    expect(dedupeKbHitsByFile(items, 15).map((x) => x.file_id)).toEqual([1, 2, 3])
  })

  it('caps at maxItems after dedupe', () => {
    const items = [hit(1), hit(2), hit(3), hit(4), hit(5)]
    expect(dedupeKbHitsByFile(items, 3)).toHaveLength(3)
    expect(dedupeKbHitsByFile(items, 3).map((x) => x.file_id)).toEqual([1, 2, 3])
  })

  it('returns fewer rows when unique files are below maxItems', () => {
    const items = [hit(10), hit(10, 1), hit(11)]
    expect(dedupeKbHitsByFile(items, 15)).toHaveLength(2)
  })
})
