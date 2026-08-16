/** Heuristic for UI hints when force reindex may touch many chunks (101 P3). */
export const KB_LARGE_DOC_CHUNK_COUNT_HINT = 500

export function isLikelyLargeDocByChunkCount(chunkCount: number | null | undefined): boolean {
  return (chunkCount ?? 0) >= KB_LARGE_DOC_CHUNK_COUNT_HINT
}
