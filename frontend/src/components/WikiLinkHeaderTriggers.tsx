import type { WikiLinkBackItem, WikiLinkOutItem } from '@/api/files'

export function uniqueBacklinkBySource(backlinks: WikiLinkBackItem[]): WikiLinkBackItem[] {
  const map = new Map<number, WikiLinkBackItem>()
  for (const bl of backlinks) {
    const prev = map.get(bl.source_file_id)
    if (!prev || (prev.broken && !bl.broken)) {
      map.set(bl.source_file_id, bl)
    }
  }
  return [...map.values()]
}

function outlinkTargetKey(ol: WikiLinkOutItem): string {
  if (ol.target_file_id != null) return `file:${ol.target_file_id}`
  if (ol.target_wiki_slug) return `wiki:${ol.target_wiki_slug}`
  return `anchor:${ol.anchor_id}`
}

export function uniqueOutlinkByTarget(outlinks: WikiLinkOutItem[]): WikiLinkOutItem[] {
  const map = new Map<string, WikiLinkOutItem>()
  for (const ol of outlinks) {
    const key = outlinkTargetKey(ol)
    const prev = map.get(key)
    if (!prev || (prev.broken && !ol.broken)) {
      map.set(key, ol)
    }
  }
  return [...map.values()]
}

function makeEntryKeyHandler(onActivate: () => void) {
  return (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onActivate()
    }
  }
}

type WikiLinkHeaderEntryProps = {
  label: string
  count: number
  onOpenList: () => void
}

function WikiLinkHeaderEntry({ label, count, onOpenList }: WikiLinkHeaderEntryProps) {
  if (count === 0) {
    return <span className="pv-header-link-stat">{label}</span>
  }

  return (
    <button
      type="button"
      className="pv-header-link-stat pv-header-link-stat-btn"
      onClick={onOpenList}
      onKeyDown={makeEntryKeyHandler(onOpenList)}
      aria-label={label}
    >
      {label}
    </button>
  )
}

type OutlinkHeaderTriggerProps = {
  label: string
  count: number
  onOpenList: () => void
}

export function OutlinkHeaderTrigger({ label, count, onOpenList }: OutlinkHeaderTriggerProps) {
  return <WikiLinkHeaderEntry label={label} count={count} onOpenList={onOpenList} />
}

type BacklinkHeaderTriggerProps = {
  label: string
  count: number
  onOpenList: () => void
}

export function BacklinkHeaderTrigger({ label, count, onOpenList }: BacklinkHeaderTriggerProps) {
  return <WikiLinkHeaderEntry label={label} count={count} onOpenList={onOpenList} />
}
