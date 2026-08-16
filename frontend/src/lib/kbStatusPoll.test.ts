import { describe, expect, it } from 'vitest'
import type { FileItem } from '@/api/files'
import { fileNeedsKbStatusPoll, listNeedsKbStatusPoll } from './kbStatusPoll'

function stubFile(overrides: Partial<FileItem>): FileItem {
  return {
    id: 1,
    filename: 'a.pdf',
    original_name: 'a.pdf',
    file_size: 1,
    mime_type: 'application/pdf',
    created_at: '',
    updated_at: '',
    has_md: false,
    index_status: 'ready',
    extract_status: 'ready',
    ...overrides,
  } as FileItem
}

describe('fileNeedsKbStatusPoll', () => {
  it('polls when index is pending or indexing', () => {
    expect(fileNeedsKbStatusPoll(stubFile({ index_status: 'pending' }))).toBe(true)
    expect(fileNeedsKbStatusPoll(stubFile({ index_status: 'indexing' }))).toBe(true)
  })

  it('polls when extract is actively running', () => {
    expect(fileNeedsKbStatusPoll(stubFile({ extract_status: 'extracting' }))).toBe(true)
  })

  it('polls when extract pending without ready indexed note', () => {
    expect(
      fileNeedsKbStatusPoll(stubFile({ extract_status: 'pending', has_md: false, index_status: 'skipped' })),
    ).toBe(true)
  })

  it('polls when extract ready but md_has_content not yet synced', () => {
    expect(
      fileNeedsKbStatusPoll(
        stubFile({
          extract_status: 'ready',
          has_md: false,
          md_has_content: false,
          original_name: 'report.pdf',
        }),
      ),
    ).toBe(true)
  })

  it('skips extract ready when md_has_content already true', () => {
    expect(
      fileNeedsKbStatusPoll(
        stubFile({
          extract_status: 'ready',
          has_md: true,
          md_has_content: true,
          original_name: 'report.pdf',
        }),
      ),
    ).toBe(false)
  })
})

describe('listNeedsKbStatusPoll', () => {
  it('returns true if any file needs poll', () => {
    expect(
      listNeedsKbStatusPoll([
        stubFile({ extract_status: 'ready', has_md: true, md_has_content: true }),
        stubFile({ extract_status: 'pending', has_md: true, index_status: 'ready' }),
      ]),
    ).toBe(false)
    expect(
      listNeedsKbStatusPoll([
        stubFile({ extract_status: 'ready' }),
        stubFile({ extract_status: 'pending', has_md: false }),
      ]),
    ).toBe(true)
  })
})
