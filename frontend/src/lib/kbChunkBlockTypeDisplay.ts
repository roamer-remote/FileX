import type { TFunction } from 'i18next'

const BLOCK_TYPE_LABEL_KEYS: Record<string, string> = {
  paragraph: 'kbChunks.blockTypeLabelParagraph',
  heading: 'kbChunks.blockTypeLabelHeading',
  table: 'kbChunks.blockTypeLabelTable',
  code: 'kbChunks.blockTypeLabelCode',
}

export function formatBlockTypeLabel(
  blockType: string | null | undefined,
  t: TFunction,
): string {
  const raw = (blockType ?? '').trim()
  if (!raw) return '—'
  const typeKey = raw.toLowerCase()
  const labelKey = BLOCK_TYPE_LABEL_KEYS[typeKey]
  if (labelKey) {
    return t('kbChunks.blockTypeDisplay', {
      label: t(labelKey),
      type: typeKey,
    })
  }
  return t('kbChunks.blockTypeDisplayUnknown', { type: raw })
}
