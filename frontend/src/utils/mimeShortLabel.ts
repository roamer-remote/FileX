/** Map MIME to short extension labels for kb_index preview and tables. */

const MIME_TO_SHORT: Record<string, string> = {
  'application/pdf': 'pdf',
  'application/msword': 'doc',
  'application/vnd.ms-powerpoint': 'ppt',
  'application/vnd.ms-excel': 'xls',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'text/plain': 'txt',
  'text/markdown': 'md',
  'text/x-markdown': 'md',
  'text/html': 'html',
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/gif': 'gif',
  'image/bmp': 'bmp',
  'image/webp': 'webp',
  'application/octet-stream': 'bin',
}

function extFromFilename(name: string | undefined): string {
  if (!name || !name.includes('.')) return ''
  const ext = name.slice(name.lastIndexOf('.') + 1).toLowerCase().trim()
  return /^[a-z0-9]{1,8}$/.test(ext) ? ext : ''
}

/** e.g. application/vnd...presentation → pptx; image/png → png */
export function mimeShortLabel(mime: string, originalName?: string): string {
  const raw = mime.trim()
  if (!raw || raw === '—' || raw === '-') return raw || '—'
  const m = raw.toLowerCase()
  if (MIME_TO_SHORT[m]) return MIME_TO_SHORT[m]
  if (!m.includes('/')) return raw
  const ext = extFromFilename(originalName)
  if (ext) return ext
  const [typ, sub] = m.split('/', 2)
  if (typ === 'image') {
    const base = sub.split('+', 1)[0]
    return base === 'jpeg' ? 'jpg' : base
  }
  if (typ === 'text') return sub === 'plain' ? 'txt' : sub.split('+', 1)[0]
  if (typ === 'application') {
    if (sub === 'pdf') return 'pdf'
    if (sub.includes('presentation') || sub.includes('powerpoint')) return 'pptx'
    if (sub.includes('wordprocessing') || sub === 'msword') return 'docx'
    if (sub.includes('spreadsheet') || sub.includes('excel')) return 'xlsx'
    const tail = sub.split('.').pop() ?? sub
    return tail.length <= 8 ? tail : tail.slice(0, 8)
  }
  const base = sub.split('+', 1)[0]
  return base.length <= 8 ? base : base.slice(0, 8)
}

function looksLikeFullMime(cell: string): boolean {
  return cell.includes('/') || cell.startsWith('application')
}

/** Preview: shorten mime_type column in kb_index AUTO tables (legacy long MIME on disk). */
export function simplifyKbIndexMimeColumn(md: string): string {
  const mimeCol = 2
  return md
    .split('\n')
    .map((line) => {
      const trimmed = line.trim()
      if (!trimmed.startsWith('|')) return line
      const inner = trimmed
        .slice(1, -1)
        .split('|')
        .map((p) => p.trim())
      if (inner.length !== 6 && inner.length !== 7) return line
      if (!/^\d+$/.test(inner[0]) && inner[0] !== '—') return line
      const mime = inner[mimeCol]
      if (!looksLikeFullMime(mime)) return line
      const next = [...inner]
      next[mimeCol] = mimeShortLabel(mime, inner[1])
      return '| ' + next.join(' | ') + ' |'
    })
    .join('\n')
}
