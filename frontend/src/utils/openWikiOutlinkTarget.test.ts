import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { WikiLinkOutItem } from '@/api/files'
import { getWikiPages } from '@/api/knowledgeBase'
import { dispatchWikiLinkNavigate } from '@/lib/wikiLinkEvents'
import { openWikiOutlinkTarget } from './openWikiOutlinkTarget'

vi.mock('@/api/knowledgeBase', () => ({
  getWikiPages: vi.fn(),
}))

vi.mock('@/lib/wikiLinkEvents', () => ({
  dispatchWikiLinkNavigate: vi.fn(),
}))

function slugOutlink(anchorId: string): WikiLinkOutItem {
  return {
    anchor_id: anchorId,
    target_file_id: null,
    target_name: null,
    target_wiki_slug: 'my-wiki-topic',
    link_kind: 'wiki',
    link_text: 'topic',
    start_offset: 0,
    end_offset: 1,
    broken: false,
    broken_reason: null,
  }
}

describe('openWikiOutlinkTarget', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('passes anchorId for direct file outlinks', async () => {
    await openWikiOutlinkTarget(
      { ...slugOutlink('sec-direct'), target_file_id: 42, target_wiki_slug: null },
      vi.fn(),
    )

    expect(dispatchWikiLinkNavigate).toHaveBeenCalledWith({ fileId: 42, anchorId: 'sec-direct' })
    expect(getWikiPages).not.toHaveBeenCalled()
  })

  it('passes anchorId after resolving slug-only outlinks', async () => {
    vi.mocked(getWikiPages).mockResolvedValue({
      items: [{ wiki_slug: 'my-wiki-topic', file_id: 77 } as never],
    } as never)

    await openWikiOutlinkTarget(slugOutlink('sec-slug'), vi.fn())

    expect(dispatchWikiLinkNavigate).toHaveBeenCalledWith({ fileId: 77, anchorId: 'sec-slug' })
  })

  it('calls onBroken when slug cannot be resolved', async () => {
    vi.mocked(getWikiPages).mockResolvedValue({ items: [] } as never)
    const onBroken = vi.fn()

    await openWikiOutlinkTarget(slugOutlink('sec-missing'), onBroken)

    expect(onBroken).toHaveBeenCalledTimes(1)
    expect(dispatchWikiLinkNavigate).not.toHaveBeenCalled()
  })
})
