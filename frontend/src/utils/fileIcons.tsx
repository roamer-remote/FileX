import {
  PictureOutlined,
  FilePdfOutlined,
  FileWordOutlined,
  FilePptOutlined,
  FileExcelOutlined,
  FileTextOutlined,
  MailOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'

export function fileTypeIcon(mimeType: string, originalName = ''): ReactNode {
  const normalizedMime = mimeType.toLowerCase()
  if (normalizedMime === 'message/rfc822' || originalName.toLowerCase().endsWith('.eml')) {
    return <MailOutlined />
  }
  if (normalizedMime.startsWith('image/')) return <PictureOutlined />
  if (normalizedMime.includes('pdf')) return <FilePdfOutlined />
  if (normalizedMime.includes('word') || normalizedMime.includes('document')) return <FileWordOutlined />
  if (normalizedMime.includes('presentation') || normalizedMime.includes('powerpoint')) return <FilePptOutlined />
  if (normalizedMime.includes('sheet') || normalizedMime.includes('excel')) return <FileExcelOutlined />
  if (normalizedMime.includes('text')) return <FileTextOutlined />
  return <FolderOpenOutlined />
}
