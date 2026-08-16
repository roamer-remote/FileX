import { describe, expect, it } from 'vitest'
import {
  outlinkListOpenable,
  outlinkOpenable,
  outlinkSlugOpenable,
  uniqueOutlinkWikiSlugs,
} from '@/utils/wikiLinkDisplay'
import type { WikiLinkOutItem } from '@/api/files'

function wikiOut(slug: string | null, extra?: Partial<WikiLinkOutItem>): WikiLinkOutItem {
  return {
    target_file_id: null,
    target_name: null,
    target_wiki_slug: slug,
    link_kind: 'wiki',
    link_text: null,
    anchor_id: 'a1',
    start_offset: 0,
    end_offset: 1,
    broken: false,
    broken_reason: null,
    ...extra,
  }
}

describe('uniqueOutlinkWikiSlugs', () => {
  it('dedupes and sorts wiki slugs from outlinks', () => {
    expect(
      uniqueOutlinkWikiSlugs([
        wikiOut('beta'),
        wikiOut('alpha'),
        wikiOut('beta'),
        wikiOut(null),
        wikiOut('  gamma  '),
      ]),
    ).toEqual(['alpha', 'beta', 'gamma'])
  })

  it('includes broken outlinks with target_wiki_slug', () => {
    expect(uniqueOutlinkWikiSlugs([wikiOut('pending-topic', { broken: true })])).toEqual(['pending-topic'])
  })
})

describe('outlinkSlugOpenable', () => {
  it('detects slug-only openable outlinks', () => {
    expect(outlinkSlugOpenable(wikiOut('my-topic'))).toBe(true)
    expect(outlinkOpenable(wikiOut('my-topic', { target_file_id: 1 }))).toBe(true)
    expect(outlinkSlugOpenable(wikiOut('my-topic', { broken: true }))).toBe(false)
  })

  it('outlinkListOpenable respects slug resolver flag', () => {
    const slugOnly = wikiOut('my-topic')
    expect(outlinkListOpenable(slugOnly, { resolveSlug: true })).toBe(true)
    expect(outlinkListOpenable(slugOnly, { resolveSlug: false })).toBe(false)
  })
})
