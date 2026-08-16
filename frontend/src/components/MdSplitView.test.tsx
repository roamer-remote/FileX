/**
 * @vitest-environment jsdom
 */

import { useState } from 'react'
import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import MdSplitView from './MdSplitView'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

const INITIAL = 'line one\nline two\nline three'

function ControlledSplitHarness({ initialPreviewHtml = '<p>preview</p>' }: { initialPreviewHtml?: string }) {
  const [source, setSource] = useState(INITIAL)
  const previewHtml = source.trim() ? initialPreviewHtml : ''
  return (
    <div style={{ height: 240, display: 'flex', flexDirection: 'column' }}>
      <MdSplitView
        source={source}
        previewHtml={previewHtml}
        fillHeight
        editable
        showHeaders={false}
        onSourceChange={setSource}
      />
    </div>
  )
}

async function renderHarness() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root: Root = createRoot(container)
  await act(async () => {
    root.render(<ControlledSplitHarness />)
  })
  const textarea = container.querySelector('textarea')
  if (!textarea) throw new Error('textarea missing')
  return { container, root, textarea }
}

function setNativeTextareaValue(textarea: HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set
  if (setter) setter.call(textarea, value)
  else textarea.value = value
}

function applyEdit(
  textarea: HTMLTextAreaElement,
  nextValue: string,
  selectionStart: number,
  selectionEnd = selectionStart,
) {
  textarea.focus()
  setNativeTextareaValue(textarea, nextValue)
  textarea.setSelectionRange(selectionStart, selectionEnd)
  act(() => {
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    textarea.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

beforeAll(() => {
  class ResizeObserverMock {
    observe() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverMock)
})

describe('MdSplitView scroll sync', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('syncs preview scroll position when source pane scrolls', async () => {
    const longSource = Array.from({ length: 80 }, (_, i) => `line ${i + 1}`).join('\n')
    const longPreview = Array.from({ length: 160 }, (_, i) => `<p>block ${i + 1}</p>`).join('\n')

    const container = document.createElement('div')
    container.style.height = '240px'
    container.style.display = 'flex'
    container.style.flexDirection = 'column'
    document.body.appendChild(container)
    const root: Root = createRoot(container)

    await act(async () => {
      root.render(
        <MdSplitView
          source={longSource}
          previewHtml={longPreview}
          fillHeight
          showHeaders={false}
        />,
      )
    })

    const srcScroll = container.querySelector('.mdsv-source-scroll') as HTMLDivElement
    const previewScroll = container.querySelector('.mdsv-preview-scroll') as HTMLDivElement
    expect(srcScroll).toBeTruthy()
    expect(previewScroll).toBeTruthy()

    Object.defineProperty(srcScroll, 'scrollHeight', { value: 2000, configurable: true })
    Object.defineProperty(srcScroll, 'clientHeight', { value: 400, configurable: true })
    Object.defineProperty(previewScroll, 'scrollHeight', { value: 4000, configurable: true })
    Object.defineProperty(previewScroll, 'clientHeight', { value: 400, configurable: true })

    srcScroll.scrollTop = 800
    act(() => {
      srcScroll.dispatchEvent(new Event('scroll', { bubbles: true }))
    })

    expect(previewScroll.scrollTop).toBe(1800)
  })

  it('re-syncs preview scroll when preview content height changes', async () => {
    class CallbackResizeObserver {
      private cb: ResizeObserverCallback
      constructor(cb: ResizeObserverCallback) {
        this.cb = cb
      }
      observe() {}
      disconnect() {}
      trigger() {
        this.cb([], this as unknown as ResizeObserver)
      }
    }

    let observer: CallbackResizeObserver | null = null
    vi.stubGlobal(
      'ResizeObserver',
      vi.fn((cb: ResizeObserverCallback) => {
        observer = new CallbackResizeObserver(cb)
        return observer
      }),
    )

    const longSource = Array.from({ length: 40 }, (_, i) => `line ${i + 1}`).join('\n')
    const preview = '<p>preview</p>'

    const container = document.createElement('div')
    container.style.height = '240px'
    document.body.appendChild(container)
    const root: Root = createRoot(container)

    await act(async () => {
      root.render(
        <MdSplitView source={longSource} previewHtml={preview} fillHeight showHeaders={false} />,
      )
    })

    const srcScroll = container.querySelector('.mdsv-source-scroll') as HTMLDivElement
    const previewScroll = container.querySelector('.mdsv-preview-scroll') as HTMLDivElement

    Object.defineProperty(srcScroll, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(srcScroll, 'clientHeight', { value: 200, configurable: true })
    Object.defineProperty(previewScroll, 'scrollHeight', { value: 500, configurable: true, writable: true })
    Object.defineProperty(previewScroll, 'clientHeight', { value: 200, configurable: true })

    srcScroll.scrollTop = 400
    act(() => {
      srcScroll.dispatchEvent(new Event('scroll', { bubbles: true }))
    })
    expect(previewScroll.scrollTop).toBe(150)

    Object.defineProperty(previewScroll, 'scrollHeight', { value: 1500, configurable: true, writable: true })
    await act(async () => {
      observer?.trigger()
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => resolve())
      })
    })

    expect(previewScroll.scrollTop).toBe(650)
  })
})

describe('MdSplitView editable fillHeight', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('keeps textarea editable when all content is cleared', async () => {
    const { textarea } = await renderHarness()
    applyEdit(textarea, '', 0)
    expect(document.querySelector('textarea')).toBe(textarea)
    expect(textarea.readOnly).toBe(false)
    expect(textarea.value).toBe('')
    applyEdit(textarea, 'restored', 8)
    expect(textarea.value).toBe('restored')
  })

  it('keeps caret after controlled source updates from typing, newline, backspace, and paste', async () => {
    const { textarea } = await renderHarness()

    const insertAt = 10
    const typed = `${INITIAL.slice(0, insertAt)}X${INITIAL.slice(insertAt)}`
    applyEdit(textarea, typed, insertAt + 1)
    expect(textarea.selectionStart).toBe(insertAt + 1)
    expect(textarea.selectionEnd).toBe(insertAt + 1)

    const withNewline = `${typed.slice(0, insertAt + 1)}\n${typed.slice(insertAt + 1)}`
    applyEdit(textarea, withNewline, insertAt + 2)
    expect(textarea.selectionStart).toBe(insertAt + 2)

    const backspaced = `${withNewline.slice(0, insertAt + 1)}${withNewline.slice(insertAt + 2)}`
    applyEdit(textarea, backspaced, insertAt + 1)
    expect(textarea.selectionStart).toBe(insertAt + 1)

    const pasted = `${backspaced.slice(0, insertAt + 1)}paste${backspaced.slice(insertAt + 1)}`
    applyEdit(textarea, pasted, insertAt + 1 + 'paste'.length)
    expect(textarea.selectionStart).toBe(insertAt + 1 + 'paste'.length)
    expect(textarea.value).toBe(pasted)
  })
})
