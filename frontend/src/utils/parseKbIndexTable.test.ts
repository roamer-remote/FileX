import { describe, expect, it } from 'vitest'
import {
  extractKbIndexProse,
  filterKbWikiIndexDisplayRows,
  filterKbIndexRows,
  hasKbWikiIndexSection,
  parseKbIndexCreatedAtMs,
  parseKbIndexRows,
  parseKbWikiIndexRows,
} from '@/utils/parseKbIndexTable'

const SAMPLE = `<!-- KB_AUTO_START -->

| file_id | original_name | mime_type | has_md | tags | created_at |
|---|---|---|---|---|---|
| 10 | alpha.pdf | pdf | yes | tag-a, tag-b | 2026-05-31 18:16:25 |
| 20 | beta.md | md | no | — | 2026-05-30 10:00:00 |

<!-- KB_AUTO_END -->`

describe('parseKbIndexTable', () => {
  it('parses AUTO table rows', () => {
    const rows = parseKbIndexRows(SAMPLE)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({
      fileId: 10,
      originalName: 'alpha.pdf',
      mimeType: 'pdf',
      hasMd: true,
      tags: ['tag-a', 'tag-b'],
      createdAt: '2026-05-31 18:16:25',
    })
    expect(rows[1].hasMd).toBe(false)
    expect(rows[1].tags).toEqual([])
  })

  it('parses created_at for sorting', () => {
    expect(parseKbIndexCreatedAtMs('2026-05-31 18:16:25')).toBeGreaterThan(
      parseKbIndexCreatedAtMs('2026-05-30 10:00:00'),
    )
    expect(parseKbIndexCreatedAtMs('—')).toBe(0)
  })
})

describe('filterKbIndexRows', () => {
  it('filters by filename, tag, mime and file id', () => {
    const rows = parseKbIndexRows(SAMPLE)
    expect(filterKbIndexRows(rows, 'alpha')).toHaveLength(1)
    expect(filterKbIndexRows(rows, 'tag-b')[0].fileId).toBe(10)
    expect(filterKbIndexRows(rows, 'md')).toHaveLength(1)
    expect(filterKbIndexRows(rows, '20')).toHaveLength(1)
    expect(filterKbIndexRows(rows, '')).toHaveLength(2)
    expect(filterKbIndexRows(rows, 'missing')).toHaveLength(0)
  })
})


const WIKI_SAMPLE = `<!-- KB_WIKI_INDEX_START -->

| file_id | wiki_slug | page_kind | original_name | outlinks | backlinks | tags |
|---|---|---|---|---|---|---|
| 42 | — | source | paper.pdf | 3 | 1 | gene |

<!-- KB_WIKI_INDEX_END -->`

describe('parseKbWikiIndexTable', () => {
  it('detects WIKI_INDEX section', () => {
    expect(hasKbWikiIndexSection(WIKI_SAMPLE)).toBe(true)
    expect(hasKbWikiIndexSection(SAMPLE)).toBe(false)
  })

  it('parses WIKI table rows', () => {
    const rows = parseKbWikiIndexRows(WIKI_SAMPLE)
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({
      fileId: 42,
      wikiSlug: '',
      pageKind: 'source',
      originalName: 'paper.pdf',
      outlinks: 3,
      backlinks: 1,
      tags: ['gene'],
    })
  })
})


describe('filterKbWikiIndexDisplayRows', () => {
  it('drops orphan source and slug topic pages without links', () => {
    const rows = parseKbWikiIndexRows(WIKI_SAMPLE)
    const mixed = [
      ...rows,
      {
        fileId: 99,
        wikiSlug: '',
        pageKind: 'source',
        originalName: 'orphan.pdf',
        outlinks: 0,
        backlinks: 0,
        tags: [],
      },
      {
        fileId: 7,
        wikiSlug: 'crispr-gene-editing',
        pageKind: 'concept',
        originalName: 'CRISPR.md',
        outlinks: 0,
        backlinks: 0,
        tags: [],
      },
    ]
    expect(filterKbWikiIndexDisplayRows(mixed)).toHaveLength(1)
    expect(filterKbWikiIndexDisplayRows(mixed)[0].fileId).toBe(42)
  })

  it('drops linked concept pages even with outlinks', () => {
    const conceptLinked = [
      {
        fileId: 8,
        wikiSlug: 'topic',
        pageKind: 'concept',
        originalName: 'Topic.md',
        outlinks: 2,
        backlinks: 0,
        tags: [],
      },
    ]
    expect(filterKbWikiIndexDisplayRows(conceptLinked)).toHaveLength(0)
  })
})

describe('extractKbIndexProse', () => {
  it('filters roamer-style tag fragment lines', () => {
    const md = `${SAMPLE}
g, 技术动态, 检索增强生成, 知识库 |
g, 技术动态, 检索增强生成, 知识库 |`
    expect(extractKbIndexProse(md)).toBe('')
  })

  it('keeps structured agent notes', () => {
    const md = `${SAMPLE}
## 本周备注

索引已在周末重建，下周关注 RAG 评测。`
    const prose = extractKbIndexProse(md)
    expect(prose).toContain('## 本周备注')
    expect(prose).toContain('索引已在周末重建')
  })

  it('returns empty when only AUTO block exists', () => {
    expect(extractKbIndexProse(SAMPLE)).toBe('')
  })
})
