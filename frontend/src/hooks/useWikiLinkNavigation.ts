import { useEffect } from 'react'
import {
  WIKI_LINK_NAVIGATE,
  dispatchWikiLinkNavigate,
  type WikiLinkNavigateDetail,
} from '@/lib/wikiLinkEvents'

export type WikiLinkOpenHandler = (fileId: number, anchorId?: string) => void

export interface UseWikiLinkNavigationResult {
  openWikiLink: (fileId: number, anchorId?: string) => void
}

/** Pure util for dispatching a wiki link open. Extracted so it can be unit tested independently of React hook rules. */
export function openWikiLink(fileId: number, anchorId?: string) {
  dispatchWikiLinkNavigate({ fileId, anchorId })
}

export function useWikiLinkNavigation(
  handler?: WikiLinkOpenHandler
): UseWikiLinkNavigationResult {
  useEffect(() => {
    if (!handler) return

    const onNavigate = (event: Event) => {
      const detail = (event as CustomEvent<WikiLinkNavigateDetail>).detail
      if (detail && typeof detail.fileId === 'number') {
        handler(detail.fileId, detail.anchorId)
      }
    }

    window.addEventListener(WIKI_LINK_NAVIGATE, onNavigate)
    return () => {
      window.removeEventListener(WIKI_LINK_NAVIGATE, onNavigate)
    }
  }, [handler])

  return {
    openWikiLink,
  }
}
