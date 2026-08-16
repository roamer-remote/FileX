import { describe, expect, it, vi } from 'vitest'
import { getExtractEngineDisplay } from '@/utils/extractEngineInfo'

const t = ((key: string, opts?: Record<string, unknown>) => {
  if (key === 'extractEngine.extractedAt') return `自动生成笔记时间：${opts?.time}`
  if (key === 'extractEngine.footerSummaryUnknown') return `未知引擎 (${opts?.raw})`
  return key
}) as never

describe('getExtractEngineDisplay', () => {
  it('hides footer when note deleted and extract idle', () => {
    expect(
      getExtractEngineDisplay(
        {
          has_md: false,
          extract_engine: 'markitdown+pymupdf-loc',
          extract_status: 'ready',
          extracted_at: '2026-06-24T09:47:34.000Z',
        },
        t,
        () => '2026-06-24 17:47:34',
      ),
    ).toBeNull()
  })

  it('hides footer while reextracting after note cleared', () => {
    expect(
      getExtractEngineDisplay(
        {
          has_md: false,
          extract_engine: 'mineru',
          extract_status: 'extracting',
          extracted_at: '2026-06-25T02:10:30.000Z',
        },
        t,
        () => '2026-06-25 02:10:30',
      ),
    ).toBeNull()
  })

  it('shows updated time when note exists', () => {
    const info = getExtractEngineDisplay(
      {
        has_md: true,
        extract_engine: 'liteparse+rapidocr',
        extract_status: 'ready',
        extracted_at: '2026-06-25T02:00:00.000Z',
      },
      t,
      () => '2026-06-25 10:00:00',
    )
    expect(info?.extractedAtLabel).toBe('自动生成笔记时间：2026-06-25 10:00:00')
  })

  it('maps pdf-inspector to a known label instead of unknown engine', () => {
    const t = ((key: string, opts?: Record<string, unknown>) => {
      if (key === 'extractEngine.engines.pdfInspector.label') return 'PDF-Inspector'
      if (key === 'extractEngine.footerSummary') return `${opts?.engine}（${opts?.raw}）`
      if (key === 'extractEngine.extractedAt') return `自动生成笔记时间：${opts?.time}`
      return key
    }) as never
    const info = getExtractEngineDisplay(
      {
        has_md: true,
        extract_engine: 'pdf-inspector',
        extract_status: 'ready',
        extracted_at: '2026-08-08T01:13:20.000Z',
      },
      t,
      () => '2026-08-08 09:13:20',
    )
    expect(info?.summary).toBe('PDF-Inspector（pdf-inspector）')
    expect(info?.rawEngine).toBe('pdf-inspector')
  })
})
