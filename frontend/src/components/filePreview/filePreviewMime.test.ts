import { describe, expect, it } from 'vitest'
import type { FileItem } from '@/api/files'
import {
  isDocxLike,
  isExcelLike,
  isEmlLike,
  isHtmlLike,
  isLegacyBinaryOffice,
  isPdfLike,
  isPptxLike,
  previewMime,
} from '@/components/filePreview/filePreviewMime'

function baseFile(overrides: Partial<FileItem>): FileItem {
  return {
    id: 1,
    filename: 'x',
    original_name: 'doc.pdf',
    file_size: 100,
    mime_type: 'application/pdf',
    folder_id: null,
    user_id: 1,
    created_at: '2026-01-01T00:00:00Z',
    has_md: false,
    md_has_content: false,
    index_status: 'ready',
    extract_status: 'ready',
    ...overrides,
  } as FileItem
}

describe('filePreviewMime', () => {
  it('detects eml by mime and extension', () => {
    expect(isEmlLike(baseFile({ original_name: 'mail.eml', mime_type: 'message/rfc822' }))).toBe(true)
    expect(isEmlLike(baseFile({ original_name: 'mail.eml', mime_type: 'application/octet-stream' }))).toBe(true)
    expect(isEmlLike(baseFile({ original_name: 'mail.txt', mime_type: 'message/rfc822' }))).toBe(true)
    expect(isEmlLike(baseFile({ original_name: 'mail.txt', mime_type: 'text/plain' }))).toBe(false)
  })

  it('detects pdf by mime and extension', () => {
    expect(isPdfLike(baseFile({ mime_type: 'application/pdf', original_name: 'a.pdf' }))).toBe(true)
    expect(isPdfLike(baseFile({ mime_type: 'text/plain', original_name: 'a.txt' }))).toBe(false)
  })

  it('detects office formats', () => {
    expect(isDocxLike(baseFile({ original_name: 'a.docx', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))).toBe(true)
    expect(isPptxLike(baseFile({ original_name: 'a.pptx', mime_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' }))).toBe(true)
    expect(isExcelLike(baseFile({ original_name: 'a.xlsx', mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))).toBe(true)
  })

  it('detects html', () => {
    expect(isHtmlLike(baseFile({ original_name: 'page.html', mime_type: 'text/html' }))).toBe(true)
  })

  it('legacy binary office when no preview_mime', () => {
    expect(isLegacyBinaryOffice(baseFile({ original_name: 'legacy.doc', mime_type: 'application/msword' }))).toBe(true)
    expect(isLegacyBinaryOffice(baseFile({ original_name: 'a.docx', mime_type: 'application/msword', preview_mime_type: 'application/pdf' }))).toBe(false)
  })

  it('previewMime prefers preview_mime_type', () => {
    const f = baseFile({ mime_type: 'application/msword', preview_mime_type: 'application/pdf', original_name: 'a.doc' })
    expect(previewMime(f)).toBe('application/pdf')
  })

  it('routes pptx with pdf preview mime to pdf renderer', () => {
    const f = baseFile({
      original_name: 'deck.pptx',
      mime_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      preview_mime_type: 'application/pdf',
    })

    expect(isPdfLike(f)).toBe(true)
    expect(isPptxLike(f)).toBe(false)
  })

  it('routes legacy ppt with pdf preview mime away from legacy office renderer', () => {
    const f = baseFile({
      original_name: 'legacy.ppt',
      mime_type: 'application/vnd.ms-powerpoint',
      preview_mime_type: 'application/pdf',
    })

    expect(isPdfLike(f)).toBe(true)
    expect(isLegacyBinaryOffice(f)).toBe(false)
  })
})
