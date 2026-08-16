/**
 * @vitest-environment jsdom
 */

import { describe, expect, it } from 'vitest'
import { syncTextareaFillHeight } from './mdSplitViewTextareaHeight'

describe('syncTextareaFillHeight', () => {
  it('preserves caret position after height sync', () => {
    const scroll = document.createElement('div')
    scroll.style.height = '120px'
    scroll.style.overflow = 'auto'
    document.body.appendChild(scroll)

    const textarea = document.createElement('textarea')
    textarea.value = 'line one\nline two\nline three'
    textarea.style.height = '40px'
    scroll.appendChild(textarea)

    textarea.focus()
    textarea.setSelectionRange(15, 15)
    scroll.scrollTop = 24
    textarea.scrollTop = 12

    syncTextareaFillHeight(textarea, scroll, 120)

    expect(textarea.selectionStart).toBe(15)
    expect(textarea.selectionEnd).toBe(15)
    expect(scroll.scrollTop).toBe(24)
    expect(textarea.scrollTop).toBe(12)
    expect(Number.parseInt(textarea.style.height, 10)).toBeGreaterThanOrEqual(120)

    scroll.remove()
  })
})
