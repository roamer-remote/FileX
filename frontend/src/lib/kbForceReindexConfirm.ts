import type { TFunction } from 'i18next'

export type ForceReindexConfirmOptions = {
  /** When true, append large-doc UX hint (many chunks). */
  largeDocHint?: boolean
  chunkCount?: number | null
}

export function buildForceReindexConfirmContent(
  t: TFunction,
  opts?: ForceReindexConfirmOptions,
): string {
  const base = t('kbChunks.forceReindexConfirmContent')
  if (!opts?.largeDocHint) {
    return base
  }
  const hint = t('kbChunks.forceReindexLargeDocHint', {
    count: opts.chunkCount ?? 0,
  })
  return `${base}\n\n${hint}`
}
