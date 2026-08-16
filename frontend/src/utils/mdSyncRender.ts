import { markedPreview } from '@/utils/markedPreview'
import type { TokensList } from 'marked'
import { sanitizeMarkdownHtml } from '@/utils/sanitizeHtml'

/** 为顶层 token 标注源码起始行（1-based），用于预览区与编辑区联动定位 */
function annotateSourceLines(src: string, tokens: TokensList): void {
  let searchPos = 0
  for (const token of tokens) {
    const raw = 'raw' in token && typeof token.raw === 'string' ? token.raw : ''
    if (!raw.length) continue
    const idx = src.indexOf(raw, searchPos)
    if (idx === -1) continue
    ;(token as { sourceLine?: number }).sourceLine = src.slice(0, idx).split('\n').length
    searchPos = idx + raw.length
  }
}

/**
 * 将 Markdown 渲染为 HTML，并为每个顶层块包一层 `me-sync-block` + `data-source-line`，
 * 便于根据光标所在行滚动预览到对应段落。
 */
export function renderMarkdownWithSyncBlocks(src: string): string {
  if (!src) return ''
  const tokens = markedPreview.lexer(src)
  annotateSourceLines(src, tokens)
  const links = tokens.links
  const parts: string[] = []
  for (const token of tokens) {
    if (token.type === 'space') continue
    const line = (token as { sourceLine?: number }).sourceLine ?? 1
    const chunk = Object.assign([token], { links }) as TokensList
    parts.push(`<div class="me-sync-block" data-source-line="${line}">${markedPreview.parser(chunk)}</div>`)
  }
  if (parts.length === 0) return sanitizeMarkdownHtml(markedPreview.parse(src) as string)
  return sanitizeMarkdownHtml(parts.join('\n'))
}

/** 根据编辑区当前行号，找到预览区应对齐的块元素（起始行不大于光标行的最近一块） */
export function findSyncBlockForLine(previewRoot: HTMLElement, line: number): HTMLElement | null {
  const blocks = previewRoot.querySelectorAll<HTMLElement>('.me-sync-block[data-source-line]')
  let best: HTMLElement | null = null
  let bestLine = -1
  blocks.forEach((el) => {
    const sl = parseInt(el.getAttribute('data-source-line') || '0', 10)
    if (!Number.isFinite(sl)) return
    if (sl <= line && sl >= bestLine) {
      bestLine = sl
      best = el
    }
  })
  return best
}
