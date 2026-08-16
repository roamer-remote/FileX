import { describe, expect, it } from 'vitest'
import {
  DEFAULT_OKF_TYPE,
  appendOkfUploadFields,
  buildOkfMetaPutPayload,
  defaultOkfTitleFromFilename,
  okfMetadataDraftFromApi,
  okfMetadataDraftFromFilename,
  okfMetadataDraftsEqual,
} from './okfMetadata'

describe('okfMetadata', () => {
  it('derives default title from filename', () => {
    expect(defaultOkfTitleFromFilename('Quarterly Report.pdf')).toBe('Quarterly Report')
    expect(defaultOkfTitleFromFilename('README')).toBe('README')
  })

  it('builds upload draft from filename with default type', () => {
    const draft = okfMetadataDraftFromFilename('notes.md')
    expect(draft.title).toBe('notes')
    expect(draft.type).toBe(DEFAULT_OKF_TYPE)
    expect(draft.tags).toEqual([])
  })

  it('appends okf upload fields to FormData', () => {
    const fd = new FormData()
    appendOkfUploadFields(
      fd,
      {
        title: 'My Doc',
        type: 'FileX Source',
        description: 'desc',
        tags: ['a', 'b'],
        conceptPath: 'sources/custom/path',
      },
      { advancedPath: true },
    )
    expect(fd.get('okf_title')).toBe('My Doc')
    expect(fd.get('okf_type')).toBe('FileX Source')
    expect(fd.get('okf_description')).toBe('desc')
    expect(fd.get('okf_tags')).toBe(JSON.stringify(['a', 'b']))
    expect(fd.get('okf_concept_path')).toBe('sources/custom/path')
  })

  it('parses API meta into draft', () => {
    const draft = okfMetadataDraftFromApi(
      {
        okf_concept_path: 'sources/x',
        okf_type: 'FileX Source',
        frontmatter: {
          title: 'T',
          description: 'D',
          tags: ['one'],
        },
      },
      'fallback',
    )
    expect(draft.title).toBe('T')
    expect(draft.description).toBe('D')
    expect(draft.tags).toEqual(['one'])
    expect(draft.conceptPath).toBe('sources/x')
  })

  it('buildOkfMetaPutPayload preserves body-only save boundary (metadata only)', () => {
    const payload = buildOkfMetaPutPayload({
      title: 'New title',
      type: 'FileX Source',
      description: '',
      tags: ['t1'],
      conceptPath: 'sources/foo',
    })
    expect(payload).toEqual({
      type: 'FileX Source',
      title: 'New title',
      description: '',
      tags: ['t1'],
      okf_concept_path: 'sources/foo',
    })
    expect(Object.keys(payload)).not.toContain('content')
    expect(Object.keys(payload)).not.toContain('body')
  })

  it('compares metadata drafts', () => {
    const a = okfMetadataDraftFromFilename('a.pdf')
    const b = okfMetadataDraftFromFilename('a.pdf')
    expect(okfMetadataDraftsEqual(a, b)).toBe(true)
    b.tags.push('x')
    expect(okfMetadataDraftsEqual(a, b)).toBe(false)
  })
})
