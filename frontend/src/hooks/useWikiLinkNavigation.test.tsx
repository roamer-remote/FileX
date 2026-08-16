import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as wikiEvents from '@/lib/wikiLinkEvents'
import { openWikiLink } from './useWikiLinkNavigation'
import { WIKI_LINK_NAVIGATE } from '@/lib/wikiLinkEvents'

describe('openWikiLink (pure util extracted for testability)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls dispatchWikiLinkNavigate with fileId and optional anchorId', () => {
    const spy = vi.spyOn(wikiEvents, 'dispatchWikiLinkNavigate')

    openWikiLink(123, 'sec-1')
    expect(spy).toHaveBeenCalledWith({ fileId: 123, anchorId: 'sec-1' })

    openWikiLink(456)
    expect(spy).toHaveBeenCalledWith({ fileId: 456, anchorId: undefined })

    spy.mockRestore()
  })
})

describe('wiki link event contract (listener side tested via manual subscription)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('listener receives valid detail and ignores invalid', () => {
    const received: any[] = []
    const listener = (ev: Event) => {
      const d = (ev as CustomEvent).detail
      if (d && typeof d.fileId === 'number') received.push(d)
    }
    window.addEventListener(WIKI_LINK_NAVIGATE, listener)

    // valid
    window.dispatchEvent(new CustomEvent(WIKI_LINK_NAVIGATE, { detail: { fileId: 77, anchorId: 'x' } }))
    // invalid
    window.dispatchEvent(new CustomEvent(WIKI_LINK_NAVIGATE, { detail: null }))
    window.dispatchEvent(new CustomEvent(WIKI_LINK_NAVIGATE, { detail: { foo: 1 } }))

    expect(received).toEqual([{ fileId: 77, anchorId: 'x' }])

    window.removeEventListener(WIKI_LINK_NAVIGATE, listener)
  })
})
