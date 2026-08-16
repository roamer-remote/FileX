export const MULTIMODAL_READONLY_KINDS = new Set(['figure', 'table', 'equation'])

export function isMultimodalReadOnlyKind(contentKind: string | null | undefined): boolean {
  if (!contentKind) return false
  return MULTIMODAL_READONLY_KINDS.has(contentKind)
}

export function multimodalKindTagColor(kind: string): string {
  switch (kind) {
    case 'figure':
      return 'blue'
    case 'table':
      return 'green'
    case 'equation':
      return 'purple'
    default:
      return 'default'
  }
}

export function formatMultimodalMetaSummary(
  kind: string | null | undefined,
  meta: Record<string, unknown> | null | undefined,
): string {
  if (!meta || typeof meta !== 'object') {
    return kind && isMultimodalReadOnlyKind(kind) ? kind : '—'
  }
  const parts: string[] = []
  if (meta.page_idx != null) parts.push(`p${String(meta.page_idx)}`)
  if (meta.slide_idx != null) parts.push(`slide ${String(meta.slide_idx)}`)
  if (meta.sheet_name) parts.push(String(meta.sheet_name))
  if (meta.caption) parts.push(String(meta.caption))
  if (meta.asset_key) {
    const key = String(meta.asset_key)
    parts.push(key.length > 28 ? `${key.slice(0, 28)}…` : key)
  }
  if (meta.figure_path && !meta.asset_key) {
    const path = String(meta.figure_path)
    parts.push(path.length > 28 ? `${path.slice(0, 28)}…` : path)
  }
  if (!parts.length && kind) return kind
  return parts.length ? parts.join(' · ') : '—'
}

export function multimodalKindI18nKey(kind: string): string {
  switch (kind) {
    case 'figure':
      return 'kbChunks.kindFigure'
    case 'table':
      return 'kbChunks.kindTable'
    case 'equation':
      return 'kbChunks.kindEquation'
    default:
      return 'kbChunks.colContentKind'
  }
}
