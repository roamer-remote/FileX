import type { WikiLinkOutItem } from '@/api/files'
import { getWikiPages } from '@/api/knowledgeBase'
import { dispatchWikiLinkNavigate } from '@/lib/wikiLinkEvents'

/** 从预览提及弹窗打开出链：file id 直连或 [[wiki:slug]] 解析，均透传 anchor_id。 */
export async function openWikiOutlinkTarget(
  ol: WikiLinkOutItem,
  onBroken: () => void,
): Promise<void> {
  if (ol.broken) return

  if (ol.target_file_id != null) {
    dispatchWikiLinkNavigate({ fileId: ol.target_file_id, anchorId: ol.anchor_id || undefined })
    return
  }

  const slug = ol.target_wiki_slug?.trim()
  if (!slug) return

  try {
    const res = await getWikiPages()
    const hit = res.items.find((p) => p.wiki_slug === slug)
    if (hit) {
      dispatchWikiLinkNavigate({ fileId: hit.file_id, anchorId: ol.anchor_id || undefined })
    } else {
      onBroken()
    }
  } catch {
    onBroken()
  }
}
