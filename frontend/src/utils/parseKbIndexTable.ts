import { mimeShortLabel, simplifyKbIndexMimeColumn } from '@/utils/mimeShortLabel'

const KB_INDEX_EN_HEADER =
  '| file_id | original_name | mime_type | has_md | tags | created_at |'

const KB_INDEX_EN_HEADER_WITH_MD5 =
  '| file_id | original_name | mime_type | md5 | has_md | tags | created_at |'

const KB_INDEX_EN_HEADER_WITH_ID =
  '| id | file_id | original_name | mime_type | md5 | has_md | tags | created_at |'

const KB_INDEX_EN_HEADER_LEGACY =
  '| id | file_id | original_name | mime_type | md5 | folder_id | has_md | tags | created_at |'

export type KbIndexRow = {
  fileId: number
  originalName: string
  mimeType: string
  hasMd: boolean
  tags: string[]
  createdAt: string
  createdAtMs: number
}

function stripKbIndexFolderIdColumn(md: string): string {
  if (!/\|\s*folder_id\s*\|/.test(md)) return md
  let out = md.split(KB_INDEX_EN_HEADER_LEGACY).join(KB_INDEX_EN_HEADER_WITH_ID)
  return out
    .split('\n')
    .map((line) => {
      const trimmed = line.trim()
      if (!trimmed.startsWith('|')) return line
      const inner = trimmed
        .slice(1, -1)
        .split('|')
        .map((p) => p.trim())
      if (inner.length !== 9) return line
      const next = [...inner.slice(0, 5), ...inner.slice(6)]
      return '| ' + next.join(' | ') + ' |'
    })
    .join('\n')
}

function stripKbIndexIdColumn(md: string): string {
  if (!/\|\s*id\s*\|\s*file_id\s*\|/.test(md)) return md
  let out = md.split(KB_INDEX_EN_HEADER_WITH_ID).join(KB_INDEX_EN_HEADER_WITH_MD5)
  return out
    .split('\n')
    .map((line) => {
      const trimmed = line.trim()
      if (!trimmed.startsWith('|')) return line
      const inner = trimmed
        .slice(1, -1)
        .split('|')
        .map((p) => p.trim())
      if (inner.length !== 8) return line
      return '| ' + inner.slice(1).join(' | ') + ' |'
    })
    .join('\n')
}

function stripKbIndexMd5Column(md: string): string {
  if (!/\|\s*mime_type\s*\|\s*md5\s*\|/i.test(md) && !/\|\s*md5\s*\|\s*has_md\s*\|/i.test(md)) return md
  let out = md.split(KB_INDEX_EN_HEADER_WITH_MD5).join(KB_INDEX_EN_HEADER)
  return out
    .split('\n')
    .map((line) => {
      const trimmed = line.trim()
      if (!trimmed.startsWith('|')) return line
      const inner = trimmed
        .slice(1, -1)
        .split('|')
        .map((p) => p.trim())
      if (inner.length !== 7) return line
      const next = [...inner.slice(0, 3), ...inner.slice(4)]
      return '| ' + next.join(' | ') + ' |'
    })
    .join('\n')
}

/** Normalize kb_index AUTO table rows for preview parsing (legacy columns + MIME labels). */
export function normalizeKbIndexMarkdown(md: string): string {
  return simplifyKbIndexMimeColumn(stripKbIndexMd5Column(stripKbIndexIdColumn(stripKbIndexFolderIdColumn(md))))
}

function parseTagsField(raw: string): string[] {
  const text = raw.trim()
  if (!text || text === '—' || text === '-') return []
  return text
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

/** Parse Beijing-style timestamp from kb_index created_at column. */
export function parseKbIndexCreatedAtMs(raw: string): number {
  const text = raw.trim()
  if (!text || text === '—' || text === '-') return 0
  const m = /^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$/.exec(text)
  if (!m) return 0
  return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]).getTime()
}

function isTableSeparatorRow(cells: string[]): boolean {
  return cells.every((c) => /^:?-{3,}:?$/.test(c.replace(/\s/g, '')) || c === '---')
}

function isPlaceholderRow(cells: string[]): boolean {
  const name = cells[1] ?? ''
  return name.includes('No files yet') || name.includes('暂无文件') || name.includes('暂无资料')
}

/** Parse AUTO table body rows from kb_index.md (preview only). */
export function parseKbIndexRows(md: string): KbIndexRow[] {
  const normalized = normalizeKbIndexMarkdown(md)
  const rows: KbIndexRow[] = []

  for (const line of normalized.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed.startsWith('|')) continue
    const cells = trimmed
      .slice(1, -1)
      .split('|')
      .map((p) => p.trim())
    if (cells.length !== 6) continue
    if (cells[0] === 'file_id' || cells[0].includes('文件') || cells[0].includes('资料')) continue
    if (isTableSeparatorRow(cells)) continue
    if (isPlaceholderRow(cells)) continue

    const fileId = parseInt(cells[0], 10)
    if (!Number.isFinite(fileId)) continue

    const mimeRaw = cells[2]
    const mimeType =
      mimeRaw.includes('/') || mimeRaw.startsWith('application')
        ? mimeShortLabel(mimeRaw, cells[1])
        : mimeRaw

    rows.push({
      fileId,
      originalName: cells[1],
      mimeType,
      hasMd: cells[3].trim().toLowerCase() === 'yes',
      tags: parseTagsField(cells[4]),
      createdAt: cells[5],
      createdAtMs: parseKbIndexCreatedAtMs(cells[5]),
    })
  }

  return rows
}

/** Markdown outside the AUTO table (agent notes, etc.), for optional preview prose. */
export function isKbIndexProseNoiseLine(line: string): boolean {
  const t = line.trim()
  if (!t) return true

  if (t.startsWith('#')) return false
  if (/^[-*+]\s/.test(t)) return false
  if (/^\d+\.\s/.test(t)) return false
  if ((t.includes('。') || t.includes('. ')) && t.length >= 20) return false

  if (t.length < 5 && !/[\u4e00-\u9fff]/.test(t) && !/[#\-*]/.test(t)) return true

  if (/^[^#\|\n]+(?:,\s*[^#\|\n]+){1,}\s*\|?\s*$/.test(t)) return true

  if (t.includes('|')) {
    const segments = t.split('|').map((s) => s.trim()).filter(Boolean)
    if (segments.length >= 2 && !t.startsWith('#')) return true
  }

  return false
}

/** Markdown outside the AUTO table (agent notes, etc.), for optional preview prose. */
export function extractKbIndexProse(md: string): string {
  return md
    .replace(/<!--\s*KB_AUTO_START\s*-->[\s\S]*?<!--\s*KB_AUTO_END\s*-->/g, '')
    .replace(/<!--\s*KB_WIKI_INDEX_START\s*-->[\s\S]*?<!--\s*KB_WIKI_INDEX_END\s*-->/g, '')
    .split('\n')
    .filter((line) => {
      const t = line.trim()
      if (!t) return false
      if (t.startsWith('|')) return false
      return !isKbIndexProseNoiseLine(line)
    })
    .join('\n')
    .trim()
}


export type KbWikiIndexRow = {
  fileId: number
  wikiSlug: string
  pageKind: string
  originalName: string
  outlinks: number
  backlinks: number
  tags: string[]
}

const WIKI_INDEX_BLOCK_RE =
  /<!--\s*KB_WIKI_INDEX_START\s*-->([\s\S]*?)<!--\s*KB_WIKI_INDEX_END\s*-->/i

export function hasKbWikiIndexSection(md: string): boolean {
  return WIKI_INDEX_BLOCK_RE.test(md)
}

export function extractKbWikiIndexInner(md: string): string | null {
  const m = WIKI_INDEX_BLOCK_RE.exec(md)
  return m ? m[1] : null
}

/** Parse WIKI_INDEX table between KB_WIKI_INDEX anchors. */
export function parseKbWikiIndexRows(md: string): KbWikiIndexRow[] {
  const inner = extractKbWikiIndexInner(md)
  if (!inner) return []

  const rows: KbWikiIndexRow[] = []
  for (const line of inner.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed.startsWith('|')) continue
    const cells = trimmed
      .slice(1, -1)
      .split('|')
      .map((p) => p.trim())
    if (cells.length !== 7) continue
    if (cells[0] === 'file_id' || cells[0].includes('文件') || cells[0].includes('资料')) continue
    if (isTableSeparatorRow(cells)) continue
    if (
      cells[3].includes('No wiki pages') ||
      cells[3].includes('No wiki-linked source files') ||
      cells[3].includes('暂无')
    )
      continue

    const fileId = parseInt(cells[0], 10)
    if (!Number.isFinite(fileId)) continue

    const outlinks = parseInt(cells[4], 10)
    const backlinks = parseInt(cells[5], 10)

    rows.push({
      fileId,
      wikiSlug: cells[1] === '—' ? '' : cells[1],
      pageKind: cells[2] === '—' ? 'source' : cells[2],
      originalName: cells[3],
      outlinks: Number.isFinite(outlinks) ? outlinks : 0,
      backlinks: Number.isFinite(backlinks) ? backlinks : 0,
      tags: parseTagsField(cells[6]),
    })
  }
  return rows
}

/** 按资料名、标签、类型或 ID 过滤 AUTO 索引行（客户端搜索）。 */
export function filterKbIndexRows(rows: KbIndexRow[], query: string): KbIndexRow[] {
  const q = query.trim().toLowerCase()
  if (!q) return rows
  return rows.filter((row) => {
    if (String(row.fileId).includes(q)) return true
    if (row.originalName.toLowerCase().includes(q)) return true
    if (row.mimeType.toLowerCase().includes(q)) return true
    return row.tags.some((tag) => tag.toLowerCase().includes(q))
  })
}

/** Web 关联信息目录：仅 source 资料且至少一条出链或入链；不含 slug 主题页。 */
export function filterKbWikiIndexDisplayRows(rows: KbWikiIndexRow[]): KbWikiIndexRow[] {
  return rows.filter(
    (r) => r.pageKind === 'source' && (r.outlinks > 0 || r.backlinks > 0),
  )
}

