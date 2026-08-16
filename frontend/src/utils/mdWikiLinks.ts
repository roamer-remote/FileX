/** 将资料 Markdown 中的 Wiki 互链语法转为可点击的 HTML 锚点（marked 允许 inline HTML）。 */
import { normalizeWikiSlug } from '@/utils/wikiSlug'

const WIKI_LINK_RE =
  /\[\[(?:([^\]|]+)\|)?(\d+)\]\]|\[\[(?:([^\]|]+)\|)?file:(\d+)\]\]|\[\[(?:([^\]|]+)\|)?wiki:([^\]\|]+)\]\]/gi

function escapeHtml(raw: string): string {
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function wikiAnchor(label: string, href: string, attrs: Record<string, string>): string {
  const attrStr = Object.entries(attrs)
    .map(([k, v]) => ` ${k}="${escapeHtml(v)}"`)
    .join('')
  return `<a href="${escapeHtml(href)}" class="wiki-link"${attrStr}>${escapeHtml(label)}</a>`
}

/**
 * [[123]] | [[file:N]] | [[wiki:slug]] | [[text|N]] | [[text|wiki:slug]]
 * → 带 data-wiki-* 的 <a class="wiki-link">，href 为 #file-N 或 #wiki-slug。
 */
export function preprocessWikiLinksForPreview(md: string): string {
  if (!md) return md
  return md.replace(WIKI_LINK_RE, (full, g1, g2, g3, g4, g5, g6) => {
    if (g2 != null) {
      const id = String(g2).trim()
      const label = (g1 != null && String(g1).trim()) || id
      return wikiAnchor(label, `#file-${id}`, { 'data-wiki-file-id': id })
    }
    if (g4 != null) {
      const id = String(g4).trim()
      const label = (g3 != null && String(g3).trim()) || id
      return wikiAnchor(label, `#file-${id}`, { 'data-wiki-file-id': id })
    }
    if (g6 != null) {
      const slug = normalizeWikiSlug(String(g6))
      if (!slug) return full
      const label = (g5 != null && String(g5).trim()) || slug
      return wikiAnchor(label, `#wiki-${slug}`, { 'data-wiki-slug': slug })
    }
    return full
  })
}
