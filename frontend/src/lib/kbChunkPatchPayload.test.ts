import { describe, expect, it } from 'vitest'
import { buildKbChunkPatchPayload } from './kbChunkPatchPayload'

describe('buildKbChunkPatchPayload', () => {
  const base = {
    originalText: 'hello world',
    editText: 'hello world',
    originalBoost: 'alpha',
    editBoost: 'alpha',
  }

  it('无变化时不发送 patch', () => {
    expect(buildKbChunkPatchPayload(base)).toEqual({ changed: false })
  })

  it('仅正文变化时发送 text 且 reembed=true，不含 boost_keywords', () => {
    const result = buildKbChunkPatchPayload({
      ...base,
      editText: 'updated body',
    })
    expect(result).toEqual({
      changed: true,
      patch: { text: 'updated body', reembed: true },
    })
  })

  it('仅 keywords 变化时发送 boost_keywords 且 reembed=false，不含 text', () => {
    const result = buildKbChunkPatchPayload({
      ...base,
      editBoost: 'beta, gamma',
    })
    expect(result).toEqual({
      changed: true,
      patch: { boost_keywords: 'beta, gamma', reembed: false },
    })
  })

  it('正文与 keywords 同时变化时两者都发送且 reembed=true', () => {
    const result = buildKbChunkPatchPayload({
      ...base,
      editText: 'new text',
      editBoost: 'kw',
    })
    expect(result).toEqual({
      changed: true,
      patch: { text: 'new text', reembed: true, boost_keywords: 'kw' },
    })
  })

  it('正文被清空时返回 empty_text 错误', () => {
    const result = buildKbChunkPatchPayload({
      ...base,
      editText: '   ',
    })
    expect(result).toEqual({ changed: true, error: 'empty_text' })
  })
})
