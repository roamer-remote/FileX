import type { TFunction } from 'i18next'

/** AUTO table: file_id, original_name, mime_type, has_md, tags, created_at */
const FILE_ID_COL_INDEX = 0
const ORIGINAL_NAME_COL_INDEX = 1
const HAS_MD_COL_INDEX = 3
const TAGS_COL_INDEX = 4

const MD_ICON_SVG =
  '<svg class="kb-index-md-icon__svg" viewBox="64 64 896 896" width="16" height="16" aria-hidden="true">' +
  '<path fill="currentColor" d="M854.6 288.6L639.4 73.4c-6-6-14.1-9.4-22.6-9.4H192c-17.7 0-32 14.3-32 32v832c0 17.7 14.3 32 32 32h640c17.7 0 32-14.3 32-32V311.3c0-8.5-3.4-16.7-9.4-22.7zM790.2 326H602V137.8L790.2 326zm1.8 562H232V136h302v216a42 42 0 0042 42h216v494z"/>' +
  '</svg>'

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function mdIconHtml(yes: boolean, t: TFunction): string {
  const label = yes ? t('knowledgeIndex.mdHasNote') : t('knowledgeIndex.mdNoNote')
  const mod = yes ? 'kb-index-md-icon--yes' : 'kb-index-md-icon--no'
  return `<span class="kb-index-md-icon ${mod}" role="img" aria-label="${label}">${MD_ICON_SVG}</span>`
}

function parseTagsCell(text: string): string[] | null {
  const raw = text.trim()
  if (!raw || raw === '—' || raw === '-') return null
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

function tagsCellHtml(tags: string[]): string {
  const title = escapeHtml(tags.join('、'))
  const chips = tags
    .map((tg) => `<span class="kb-index-tags-chip">${escapeHtml(tg)}</span>`)
    .join('')
  return (
    `<div class="kb-index-tags" title="${title}">` +
    `<div class="kb-index-tags-track">` +
    `<div class="kb-index-tags-strip">${chips}</div>` +
    `</div></div>`
  )
}

function withKbIndexRoot(html: string, fn: (root: HTMLElement) => void): string {
  if (!html.includes('<table')) return html
  const doc = new DOMParser().parseFromString(`<div id="kb-root">${html}</div>`, 'text/html')
  const root = doc.getElementById('kb-root')
  if (!root) return html
  fn(root)
  return root.innerHTML
}

/** Replace has_md yes/no cells with note icons (preview HTML only). */
export function iconifyKbIndexHasMdColumn(html: string, t: TFunction): string {
  return withKbIndexRoot(html, (root) => {
    root.querySelectorAll('table tbody tr').forEach((tr) => {
      const cells = tr.querySelectorAll('td')
      if (cells.length <= HAS_MD_COL_INDEX) return
      const cell = cells[HAS_MD_COL_INDEX]
      const raw = (cell.textContent ?? '').trim().toLowerCase()
      if (raw === 'yes') cell.innerHTML = mdIconHtml(true, t)
      else if (raw === 'no') cell.innerHTML = mdIconHtml(false, t)
    })
  })
}

/** Make filename cells open file preview (preview HTML only). */
export function linkifyKbIndexFilenameColumn(html: string): string {
  return withKbIndexRoot(html, (root) => {
    root.querySelectorAll('table tbody tr').forEach((tr) => {
      const cells = tr.querySelectorAll('td')
      if (cells.length <= ORIGINAL_NAME_COL_INDEX) return
      const idRaw = (cells[FILE_ID_COL_INDEX].textContent ?? '').trim()
      const fileId = parseInt(idRaw, 10)
      if (!Number.isFinite(fileId)) return
      const nameCell = cells[ORIGINAL_NAME_COL_INDEX]
      const name = (nameCell.textContent ?? '').trim()
      if (!name) return
      const safeName = escapeHtml(name)
      nameCell.innerHTML =
        `<button type="button" class="kb-index-filename-link" data-file-id="${fileId}" ` +
        `title="${safeName}">${safeName}</button>`
    })
  })
}

/** Wrap tags cell for marquee (preview HTML only). */
export function decorateKbIndexTagsColumn(html: string): string {
  return withKbIndexRoot(html, (root) => {
    root.querySelectorAll('table tbody tr').forEach((tr) => {
      const cells = tr.querySelectorAll('td')
      if (cells.length <= TAGS_COL_INDEX) return
      const cell = cells[TAGS_COL_INDEX]
      const tags = parseTagsCell(cell.textContent ?? '')
      if (!tags?.length) return
      cell.innerHTML = tagsCellHtml(tags)
    })
  })
}

export function enhanceKbIndexPreviewHtml(html: string, t: TFunction): string {
  return linkifyKbIndexFilenameColumn(
    decorateKbIndexTagsColumn(iconifyKbIndexHasMdColumn(html, t)),
  )
}

/** Measure overflow / multi-line tags and enable seamless marquee. */
export function setupKbIndexTagsMarquee(previewRoot: HTMLElement): () => void {
  const measure = () => {
    previewRoot.querySelectorAll<HTMLElement>('.kb-index-tags:not([data-marquee-managed="react"])').forEach((vp) => {
      const track = vp.querySelector<HTMLElement>('.kb-index-tags-track')
      const strip = vp.querySelector<HTMLElement>('.kb-index-tags-strip')
      if (!track || !strip) return

      const oneLine = parseFloat(getComputedStyle(strip).lineHeight) || 20
      const overflowX = strip.scrollWidth > vp.clientWidth + 1
      const overflowY = strip.scrollHeight > oneLine + 2
      const marquee = overflowX || overflowY

      track.classList.toggle('kb-index-tags-track--marquee', marquee)
      const dup = track.querySelector('.kb-index-tags-strip[aria-hidden]')
      if (marquee) {
        if (!dup) {
          const clone = strip.cloneNode(true) as HTMLElement
          clone.setAttribute('aria-hidden', 'true')
          track.appendChild(clone)
        }
        const w = strip.scrollWidth
        vp.style.setProperty('--kb-tags-marquee-sec', `${Math.min(48, Math.max(8, w / 26))}s`)
        const label = (strip.textContent ?? '').trim()
        if (label) vp.setAttribute('title', label)
      } else {
        dup?.remove()
        vp.style.removeProperty('--kb-tags-marquee-sec')
      }
    })
  }

  measure()
  const ro = new ResizeObserver(measure)
  ro.observe(previewRoot)
  previewRoot.querySelectorAll('.kb-index-tags').forEach((el) => ro.observe(el))
  return () => ro.disconnect()
}
