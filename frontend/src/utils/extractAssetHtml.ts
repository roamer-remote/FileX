/** extract-assets 预览 HTML 占位与 src 解析（无 API 依赖，供 marked 输出与 hydration 共用）。 */

/** 1×1 透明 GIF，避免 hydration 前浏览器直载 legacy API URL 产生 401 */
export const EXTRACT_ASSET_PLACEHOLDER_SRC =
  'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

const EXTRACT_ASSET_IMAGE_RE = /!\[([^\]]*)\]\(([^)]+)\)/g
const IMAGE_EXT_RE = /\.(jpe?g|png|gif|webp|bmp|svg)$/i
const URL_SCHEME_RE = /^[a-z][a-z\d+.-]*:/i

function extractAssetPreviewUrl(fileId: number, assetKey: string): string {
  return `/api/files/${fileId}/extract-assets/${encodeURIComponent(assetKey)}`
}

function extractAssetFileIdFromPath(url: string): number | null {
  const match = url.match(/(?:^|\/)\.extract_assets\/(\d+)(?:\/|$)/)
  if (!match) return null
  const parsed = Number.parseInt(match[1], 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function splitMarkdownImageDestination(raw: string): { url: string; suffix: string } | null {
  const trimmed = raw.trim()
  if (!trimmed) return null
  if (trimmed.startsWith('<')) {
    const end = trimmed.indexOf('>')
    if (end <= 1) return null
    return {
      url: trimmed.slice(1, end).trim(),
      suffix: trimmed.slice(end + 1),
    }
  }
  const match = trimmed.match(/^(\S+)(.*)$/)
  if (!match) return null
  return { url: match[1], suffix: match[2] ?? '' }
}

function isRelativeImageUrl(url: string): boolean {
  if (
    !url ||
    url.startsWith('/') ||
    url.startsWith('#') ||
    url.startsWith('?') ||
    url.startsWith('//') ||
    URL_SCHEME_RE.test(url)
  ) {
    return false
  }
  return IMAGE_EXT_RE.test(url.replace(/\\/g, '/').split('/').pop() ?? '')
}

function isLocalExtractAssetUrl(url: string): boolean {
  if (!url.includes('.extract_assets/')) return false
  return !URL_SCHEME_RE.test(url) && !url.startsWith('//')
}

/** MinerU 笔记内相对资产路径 → extract-assets API URL（后续由 preprocessExtractAssetImgTags 换占位） */
export function preprocessExtractAssetImages(md: string, fileId: number): string {
  if (!md || !fileId) return md
  return md.replace(EXTRACT_ASSET_IMAGE_RE, (match, alt: string, url: string) => {
    const parsed = splitMarkdownImageDestination(url)
    if (!parsed) return match
    const normalizedUrl = parsed.url.replace(/\\/g, '/')
    if (!isLocalExtractAssetUrl(normalizedUrl) && !isRelativeImageUrl(normalizedUrl)) {
      return match
    }
    const base = normalizedUrl.split('/').pop()
    if (!base || !IMAGE_EXT_RE.test(base)) return match
    const assetFileId = extractAssetFileIdFromPath(normalizedUrl) ?? fileId
    return `![${alt}](${extractAssetPreviewUrl(assetFileId, base)}${parsed.suffix})`
  })
}

export function parseExtractAssetKeyFromApiSrc(src: string): string | null {
  const match = src.match(/\/api\/files\/\d+\/extract-assets\/([^?#]+)/)
  if (!match) return null
  try {
    return decodeURIComponent(match[1])
  } catch {
    return null
  }
}

export function parseExtractAssetFileIdFromApiSrc(src: string): number | null {
  const match = src.match(/\/api\/files\/(\d+)\/extract-assets\//)
  if (!match) return null
  const parsed = Number.parseInt(match[1], 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

/** Match legacy extract-assets API src (src may be first attribute after `<img`). */
const EXTRACT_ASSET_IMG_TAG_RE =
  /<img\b(?=[^>]*\ssrc=)([^>]*?\s)src=(["'])(\/api\/files\/\d+\/extract-assets\/[^"'?#]+)\2([^>]*)>/gi

function escapeHtmlAttr(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;')
}

/** marked HTML → 占位 src + data-extract-asset-key，避免 dangerouslySetInnerHTML 直载 legacy URL（105 FR-105-003） */
export function preprocessExtractAssetImgTags(html: string): string {
  if (!html) return html
  return html.replace(EXTRACT_ASSET_IMG_TAG_RE, (full, before, quote, src, after) => {
    if (
      String(before).includes('data-extract-asset-key') ||
      String(after).includes('data-extract-asset-key')
    ) {
      return full
    }
    const key = parseExtractAssetKeyFromApiSrc(src)
    if (!key) return full
    const assetFileId = parseExtractAssetFileIdFromApiSrc(src)
    const fileIdAttr = assetFileId ? ` data-extract-asset-file-id="${assetFileId}"` : ''
    return `<img${before}src=${quote}${EXTRACT_ASSET_PLACEHOLDER_SRC}${quote}${fileIdAttr} data-extract-asset-fallback-src="${escapeHtmlAttr(src)}" data-extract-asset-key="${escapeHtmlAttr(key)}"${after}>`
  })
}
