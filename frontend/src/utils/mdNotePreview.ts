import type { FileTagAnchorItem, WikiLinkOutItem, FileItem } from '@/api/files'
import {
  anchorBelongsToNote,
  injectAnchorSpans,
  mergeNoteAnchorHits,
  scrollAnchorInNoteRoot,
  type AnchorScrollHint,
} from '@/utils/mdTagAnchors'
import { markdownToSafeHtml } from '@/utils/markdownPreview'

const WIKI_TOPIC_PAGE_KINDS = new Set(['entity', 'concept', 'synthesis'])

export function isWikiThemePage(f: FileItem): boolean {
  return WIKI_TOPIC_PAGE_KINDS.has(f.page_kind ?? 'source')
}

export function renderNotePreviewHtml(
  raw: string,
  tagAnchors: FileTagAnchorItem[],
  wikiOutlinks: WikiLinkOutItem[],
  fileId?: number,
): string {
  const withSpans = injectAnchorSpans(raw, mergeNoteAnchorHits(tagAnchors, wikiOutlinks))
  return markdownToSafeHtml(withSpans, fileId ? { fileId } : undefined)
}

/** 等待下一帧绘制，确保 antd Modal 等 Portal 子节点已挂载且 ref 可用 */
export function waitPaintFrames(frames = 2): Promise<void> {
  let chain = Promise.resolve()
  for (let i = 0; i < frames; i++) {
    chain = chain.then(
      () =>
        new Promise<void>((resolve) => {
          requestAnimationFrame(() => resolve())
        }),
    )
  }
  return chain
}

export function anchorScrollHint(
  tagAnchors: FileTagAnchorItem[],
  wikiOutlinks: WikiLinkOutItem[],
  anchorId: string,
  raw: string,
): AnchorScrollHint | undefined {
  const tagHit = tagAnchors.find((a) => a.anchor_id === anchorId)
  if (tagHit) return { raw, tag: tagHit.tag, start: tagHit.start_offset, end: tagHit.end_offset }
  const wikiHit = wikiOutlinks.find((o) => o.anchor_id === anchorId)
  if (wikiHit) return { raw, start: wikiHit.start_offset, end: wikiHit.end_offset }
  return { raw }
}

export async function scrollToAnchorWithRetry(
  noteRoot: HTMLElement,
  anchorId: string,
  hint: AnchorScrollHint | undefined,
  maxAttempts = 10,
): Promise<boolean> {
  for (let i = 0; i < maxAttempts; i++) {
    if (scrollAnchorInNoteRoot(noteRoot, anchorId, hint)) return true
    await waitPaintFrames(1)
  }
  return false
}

export function bindWikiLinkClick(root: HTMLElement, onActivate: (el: HTMLAnchorElement) => void) {
  const onClick = (ev: MouseEvent) => {
    const target = ev.target
    if (!(target instanceof Element)) return
    const anchor = target.closest('a.wiki-link')
    if (!(anchor instanceof HTMLAnchorElement) || !root.contains(anchor)) return
    ev.preventDefault()
    onActivate(anchor)
  }
  root.addEventListener('click', onClick)
  return () => root.removeEventListener('click', onClick)
}

export { anchorBelongsToNote }
