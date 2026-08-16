import DOMPurify from 'isomorphic-dompurify'

/**
 * marked 预览 + wiki 互链 / 锚点 / sync-block / KaTeX 所需属性。
 * `style` 为 KaTeX 布局所需（height、margin 等）；DOMPurify 不校验 CSS 值，
 * 本项目为用户自有内容 + 既有 dangerouslySetInnerHTML 模式，风险可控。
 */
const MARKDOWN_PURIFY_CONFIG = {
  ADD_ATTR: [
    'data-wiki-file-id',
    'data-wiki-slug',
    'data-source-line',
    'data-extract-asset-key',
    'target',
    'rel',
    'id',
    'class',
    'aria-hidden',
    'style',
  ],
  ADD_TAGS: ['span'],
}

const SPREADSHEET_PURIFY_CONFIG = {
  ALLOWED_TAGS: ['table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'col', 'colgroup'],
  ALLOWED_ATTR: ['colspan', 'rowspan', 'scope', 'class'],
}

export function sanitizeMarkdownHtml(dirty: string): string {
  if (!dirty) return ''
  return DOMPurify.sanitize(dirty, MARKDOWN_PURIFY_CONFIG)
}

export function sanitizeSpreadsheetHtml(dirty: string): string {
  if (!dirty) return ''
  return DOMPurify.sanitize(dirty, SPREADSHEET_PURIFY_CONFIG)
}
