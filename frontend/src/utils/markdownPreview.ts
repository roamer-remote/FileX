import katex from 'katex'
import { markedPreview } from '@/utils/markedPreview'
import { preprocessWikiLinksForPreview } from '@/utils/mdWikiLinks'
import { preprocessExtractAssetImages, preprocessExtractAssetImgTags } from '@/utils/extractAssetHtml'
import { sanitizeMarkdownHtml } from '@/utils/sanitizeHtml'

export { hydrateExtractAssetImages } from '@/utils/extractAssetHydration'
export { preprocessExtractAssetImages } from '@/utils/extractAssetHtml'

export type MarkdownPreviewOptions = {
  /** 默认 true：展开 [[wiki:]] / [[file:]] 互链 */
  wikiLinks?: boolean
  /** 资料 ID：将 `.extract_assets/` 相对路径改写为 extract-assets API URL */
  fileId?: number
}

/** MinerU sidecar：`filex:content kind=equation` 后的 fenced LaTeX → 块级 $$ 供 KaTeX 渲染（保留 marker 供索引） */
export function preprocessFilexEquationBlocks(md: string): string {
  if (!md.includes('filex:content') || !md.includes('kind=equation')) return md
  return md.replace(
    /(<!--\s*filex:content\s+kind=equation[^>]*-->\s*)```(?:[^\n]*\n)?([\s\S]*?)```/gi,
    (_full, marker: string, body: string) => equationBlockToPreviewMarkdown(marker, body),
  )
}

function stripEquationDelimiters(body: string): string {
  return body.trim().replace(/^\$\$\s*/, '').replace(/\s*\$\$$/, '')
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function equationBlockToPreviewMarkdown(marker: string, body: string): string {
  const trimmed = body.trim()
  if (!trimmed) return marker
  const inner = stripEquationDelimiters(trimmed)
  if (!inner) return marker
  try {
    katex.renderToString(inner, { throwOnError: true, displayMode: true, output: 'html' })
    const display = /^\$\$[\s\S]*\$\$$/.test(trimmed) ? trimmed : `$$\n${inner}\n$$`
    return `${marker}\n\n${display}\n`
  } catch {
    return `${marker}\n\n<div class="filex-equation-fallback"><p class="filex-equation-fallback-hint">公式无法自动渲染（OCR 提取的 LaTeX 语法不完整），原文如下：</p><pre class="filex-equation-source"><code>${escapeHtml(inner)}</code></pre></div>\n`
  }
}

/** 用户 Markdown → 经 marked 渲染并 DOMPurify 消毒，供 dangerouslySetInnerHTML 使用 */
export function markdownToSafeHtml(md: string, options?: MarkdownPreviewOptions): string {
  if (!md) return ''
  const wikiLinks = options?.wikiLinks !== false
  let src = preprocessFilexEquationBlocks(md)
  src = wikiLinks ? preprocessWikiLinksForPreview(src) : src
  if (options?.fileId) {
    src = preprocessExtractAssetImages(src, options.fileId)
  }
  const rendered = markedPreview.parse(src) as string
  const withPlaceholderAssets = options?.fileId ? preprocessExtractAssetImgTags(rendered) : rendered
  return sanitizeMarkdownHtml(withPlaceholderAssets)
}
