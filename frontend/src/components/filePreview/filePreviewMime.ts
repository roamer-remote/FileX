import type { FileItem } from '@/api/files'

export function isMarkdownSourceFile(f: FileItem): boolean {
  return f.mime_type === 'text/markdown'
}

export function isEmlLike(f: FileItem): boolean {
  return f.original_name.toLowerCase().endsWith('.eml') || f.mime_type.toLowerCase() === 'message/rfc822'
}

export function previewMime(f: FileItem): string {
  return (f.preview_mime_type || f.mime_type).toLowerCase()
}

export function isExtractBusy(status: string | undefined): boolean {
  return status === 'pending' || status === 'extracting'
}

export function isPdfLike(f: FileItem): boolean {
  const m = previewMime(f)
  return (
    m === 'application/pdf' ||
    m.includes('pdf') ||
    f.original_name.toLowerCase().endsWith('.pdf')
  )
}

export function isHtmlLike(f: FileItem): boolean {
  const name = f.original_name.toLowerCase()
  const m = f.mime_type.toLowerCase()
  return (
    name.endsWith('.html') ||
    name.endsWith('.htm') ||
    m.includes('text/html') ||
    m.includes('application/xhtml+xml')
  )
}

export function isDocxLike(f: FileItem): boolean {
  const name = f.original_name.toLowerCase()
  const m = previewMime(f)
  return name.endsWith('.docx') || m.includes('wordprocessingml.document')
}

export function isPptxLike(f: FileItem): boolean {
  if (isPdfLike(f)) return false
  const name = f.original_name.toLowerCase()
  const m = previewMime(f)
  return name.endsWith('.pptx') || m.includes('presentationml.presentation')
}

export function isLegacyBinaryOffice(f: FileItem): boolean {
  if (f.preview_mime_type) return false
  const name = f.original_name.toLowerCase()
  const m = f.mime_type.toLowerCase()
  if (name.endsWith('.docx') || name.endsWith('.pptx')) return false
  if (m === 'application/msword' || name.endsWith('.doc')) return true
  if (m === 'application/vnd.ms-powerpoint' || name.endsWith('.ppt')) return true
  return false
}

export function isLegacyDocForPreview(f: FileItem): boolean {
  if (f.preview_mime_type) return false
  const name = f.original_name.toLowerCase()
  const m = f.mime_type.toLowerCase()
  if (name.endsWith('.docx')) return false
  return name.endsWith('.doc') || m === 'application/msword'
}

export function isLegacyPptForPreview(f: FileItem): boolean {
  if (f.preview_mime_type) return false
  const name = f.original_name.toLowerCase()
  const m = f.mime_type.toLowerCase()
  if (name.endsWith('.pptx')) return false
  return name.endsWith('.ppt') || m === 'application/vnd.ms-powerpoint'
}

/** Excel 工作簿（.xlsx / .xls），浏览器内表格预览 */
export function isExcelLike(f: FileItem): boolean {
  const name = f.original_name.toLowerCase()
  const m = previewMime(f)
  return (
    name.endsWith('.xlsx') ||
    name.endsWith('.xls') ||
    m.includes('spreadsheetml.sheet') ||
    m.includes('ms-excel') ||
    m === 'application/vnd.ms-excel'
  )
}

export type ExcelPreviewTab = { key: string; label: string; html: string }
