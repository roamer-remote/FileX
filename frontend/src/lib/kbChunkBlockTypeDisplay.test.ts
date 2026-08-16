import type { TFunction } from 'i18next'
import { describe, expect, it } from 'vitest'
import { formatBlockTypeLabel } from './kbChunkBlockTypeDisplay'

function makeT(locale: 'zh' | 'en'): TFunction {
  const labelsZh: Record<string, string> = {
    'kbChunks.blockTypeLabelParagraph': '段落',
    'kbChunks.blockTypeLabelHeading': '标题',
    'kbChunks.blockTypeLabelTable': '表格',
    'kbChunks.blockTypeLabelCode': '代码',
  }
  const labelsEn: Record<string, string> = {
    'kbChunks.blockTypeLabelParagraph': 'Paragraph',
    'kbChunks.blockTypeLabelHeading': 'Heading',
    'kbChunks.blockTypeLabelTable': 'Table',
    'kbChunks.blockTypeLabelCode': 'Code',
  }
  const labels = locale === 'zh' ? labelsZh : labelsEn
  return ((key: string, opts?: { label?: string; type?: string }) => {
    if (key === 'kbChunks.blockTypeDisplay' && opts?.label != null && opts?.type != null) {
      return locale === 'zh'
        ? `${opts.label}（${opts.type}）`
        : opts.label
    }
    if (key === 'kbChunks.blockTypeDisplayUnknown' && opts?.type != null) {
      return locale === 'zh' ? `${opts.type}（${opts.type}）` : opts.type
    }
    return labels[key] ?? key
  }) as TFunction
}

describe('formatBlockTypeLabel', () => {
  it('zh：段落/标题 显示为中文（英文 slug）', () => {
    const t = makeT('zh')
    expect(formatBlockTypeLabel('paragraph', t)).toBe('段落（paragraph）')
    expect(formatBlockTypeLabel('heading', t)).toBe('标题（heading）')
  })

  it('en：仅显示本地化标签', () => {
    const t = makeT('en')
    expect(formatBlockTypeLabel('paragraph', t)).toBe('Paragraph')
    expect(formatBlockTypeLabel('heading', t)).toBe('Heading')
  })

  it('空值显示 —', () => {
    expect(formatBlockTypeLabel(null, makeT('zh'))).toBe('—')
    expect(formatBlockTypeLabel('  ', makeT('zh'))).toBe('—')
  })

  it('未知类型 fallback', () => {
    expect(formatBlockTypeLabel('custom', makeT('zh'))).toBe('custom（custom）')
    expect(formatBlockTypeLabel('custom', makeT('en'))).toBe('custom')
  })
})
