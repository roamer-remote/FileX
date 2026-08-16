import type { KbChunkHit } from '@/api/knowledgeBase'

/** 智能检索：按 file_id 严格去重，保留 API 返回顺序，最多 maxItems 条。 */
export function dedupeKbHitsByFile(items: KbChunkHit[], maxItems: number): KbChunkHit[] {
  const limit = Math.max(0, Math.floor(maxItems))
  if (limit === 0) return []

  const seen = new Set<number>()
  const out: KbChunkHit[] = []
  for (const hit of items) {
    const fid = hit.file_id
    if (seen.has(fid)) continue
    seen.add(fid)
    out.push(hit)
    if (out.length >= limit) break
  }
  return out
}
