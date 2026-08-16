/** 与后端生成的 anchor_id 一致：字母数字、下划线、连字符 */
const ANCHOR_ID_RE = /^[a-zA-Z0-9_-]+$/

export type AnchorHit = { anchor_id: string; start: number; end: number; tag?: string }

/**
 * 在原始 Markdown 的标签词起始处插入空 <span id="..."></span>（不包裹正文），
 * 避免破坏 [[wiki]] 等语法；须按 start 降序插入以免偏移错位。
 */
export function injectAnchorSpans(markdown: string, hits: AnchorHit[]): string {
  const sorted = [...hits]
    .filter((h) => ANCHOR_ID_RE.test(h.anchor_id))
    .sort((a, b) => b.start - a.start)
  let out = markdown
  for (const h of sorted) {
    const { start, end, anchor_id, tag } = h
    if (start < 0 || end > out.length || start >= end) continue
    const slice = out.slice(start, end)
    if (tag != null && tag.length > 0 && slice.toLowerCase() !== tag.toLowerCase()) continue
    out = `${out.slice(0, start)}<span id="${anchor_id}"></span>${out.slice(start)}`
  }
  return out
}

export type AnchorScrollHint = {
  tag?: string
  start?: number
  end?: number
  /** 资料笔记原始 Markdown，用于文本回退定位 */
  raw?: string
}

function scrollElementIntoNoteModal(el: HTMLElement, noteRoot: HTMLElement): boolean {
  const modalBody =
    (typeof el.closest === "function" && el.closest(".ant-modal-body")) ||
    (typeof noteRoot.closest === "function" && noteRoot.closest(".ant-modal-body"))
  if (modalBody instanceof HTMLElement && modalBody.scrollHeight > modalBody.clientHeight + 1) {
    const er = el.getBoundingClientRect()
    const br = modalBody.getBoundingClientRect()
    const delta = er.top + er.height / 2 - (br.top + modalBody.clientHeight / 2)
    modalBody.scrollTo({ top: Math.max(0, modalBody.scrollTop + delta), behavior: "smooth" })
    return true
  }
  el.scrollIntoView({ block: "center", behavior: "smooth" })
  return true
}

/** 在笔记 HTML 容器内滚动到锚点；找不到 id 时按原文偏移匹配可见文本 */
export function scrollAnchorInNoteRoot(
  noteRoot: HTMLElement,
  anchorId: string,
  hint?: AnchorScrollHint,
): boolean {
  let el: Element | null = null
  try {
    el = noteRoot.querySelector(`#${CSS.escape(anchorId)}`)
  } catch {
    el = null
  }
  if (el instanceof HTMLElement) {
    scrollElementIntoNoteModal(el, noteRoot)
    return true
  }

  const raw = hint?.raw
  const start = hint?.start
  const end = hint?.end
  if (raw != null && start != null && end != null && start >= 0 && end > start && end <= raw.length) {
    const needle = raw.slice(start, end)
    if (needle.length > 0) {
      const tw = document.createTreeWalker(noteRoot, NodeFilter.SHOW_TEXT)
      let node: Node | null
      while ((node = tw.nextNode())) {
        const text = node.textContent ?? ""
        const idx = text.indexOf(needle)
        if (idx < 0) continue
        const range = document.createRange()
        range.setStart(node, idx)
        range.setEnd(node, idx + needle.length)
        const rect = range.getBoundingClientRect()
        if (rect.height === 0 && rect.width === 0) continue
        const marker = document.createElement("span")
        marker.style.scrollMarginTop = "12vh"
        range.insertNode(marker)
        scrollElementIntoNoteModal(marker, noteRoot)
        marker.remove()
        return true
      }
    }
  }

  return false
}


export function mergeNoteAnchorHits(
  tagAnchors: { anchor_id: string; start_offset: number; end_offset: number; tag: string }[],
  wikiOutlinks: { anchor_id: string; start_offset: number; end_offset: number }[],
): AnchorHit[] {
  const hits: AnchorHit[] = tagAnchors.map((a) => ({
    anchor_id: a.anchor_id,
    start: a.start_offset,
    end: a.end_offset,
    tag: a.tag,
  }))
  for (const o of wikiOutlinks) {
    if (Number.isFinite(o.start_offset) && Number.isFinite(o.end_offset) && o.end_offset > o.start_offset) {
      hits.push({ anchor_id: o.anchor_id, start: o.start_offset, end: o.end_offset })
    }
  }
  return hits
}

export function anchorBelongsToNote(
  anchorId: string,
  tagAnchors: { anchor_id: string }[],
  wikiOutlinks: { anchor_id: string }[],
): boolean {
  return tagAnchors.some((a) => a.anchor_id === anchorId) || wikiOutlinks.some((o) => o.anchor_id === anchorId)
}
