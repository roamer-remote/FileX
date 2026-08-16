export { copyToClipboard } from './copyToClipboard'

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
}

export function getFileIcon(mimeType: string): string {
  if (mimeType.startsWith('image/')) return 'Picture'
  if (mimeType.includes('pdf')) return 'Document'
  if (mimeType.includes('word') || mimeType.includes('document')) return 'Document'
  if (mimeType.includes('presentation') || mimeType.includes('powerpoint')) return 'DataAnalysis'
  if (mimeType.includes('sheet') || mimeType.includes('excel')) return 'DataLine'
  if (mimeType.includes('text')) return 'Memo'
  return 'FolderOpened'
}

export function isPreviewable(mimeType: string): boolean {
  if (mimeType.startsWith('image/')) return true
  if (mimeType.includes('pdf')) return true
  const m = mimeType.toLowerCase()
  if (m.includes('wordprocessingml.document')) return true
  if (m.includes('presentationml.presentation')) return true
  return false
}

export function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  const s = String(date.getSeconds()).padStart(2, '0')
  return `${y}-${m}-${d} ${h}:${min}:${s}`
}
