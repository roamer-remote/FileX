import type { WikiLinkBackItem, WikiLinkOutItem } from '@/api/files'

export function outlinkRowLabel(ol: WikiLinkOutItem): string {
  if (ol.target_name?.trim()) return ol.target_name.trim()
  if (ol.link_text?.trim()) return ol.link_text.trim()
  if (ol.target_wiki_slug) return ol.target_wiki_slug
  return ol.anchor_id
}

export function brokenOutlinkRowLabel(ol: WikiLinkOutItem): string | null {
  if (ol.target_wiki_slug?.trim()) return ol.target_wiki_slug.trim()
  if (ol.link_text?.trim()) return ol.link_text.trim()
  return null
}

export function backlinkRowLabel(bl: WikiLinkBackItem): string {
  const name = bl.source_name?.trim() || String(bl.source_file_id)
  const text = bl.link_text?.trim()
  return text && text !== name ? `${name}（${text}）` : name
}

export function outlinkOpenable(ol: WikiLinkOutItem): ol is WikiLinkOutItem & { target_file_id: number } {
  return !ol.broken && ol.target_file_id != null
}

/** [[wiki:slug]] 出链：无 target_file_id 但 slug 可解析为 Wiki 页 */
export function outlinkSlugOpenable(ol: WikiLinkOutItem): boolean {
  return !ol.broken && ol.target_file_id == null && Boolean(ol.target_wiki_slug?.trim())
}

export function outlinkListOpenable(
  ol: WikiLinkOutItem,
  opts?: { resolveSlug?: boolean },
): boolean {
  return outlinkOpenable(ol) || (opts?.resolveSlug !== false && outlinkSlugOpenable(ol))
}

export function backlinkOpenable(bl: WikiLinkBackItem): boolean {
  return !bl.broken && bl.source_file_id > 0
}

/** 出链中去重、排序后的 [[wiki:slug]] 目标（含断链待编译）。 */
export function uniqueOutlinkWikiSlugs(outlinks: WikiLinkOutItem[]): string[] {
  const seen = new Set<string>()
  const slugs: string[] = []
  for (const ol of outlinks) {
    const slug = ol.target_wiki_slug?.trim()
    if (!slug || seen.has(slug)) continue
    seen.add(slug)
    slugs.push(slug)
  }
  return slugs.sort((a, b) => a.localeCompare(b))
}
