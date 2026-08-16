/** 关系网络：按文件团块分区布局，共享 tag 节点坐标合并 */

import {
  layoutComponentForce,
  type TagGraphLinkLike,
  type TagGraphNodeLike,
  type TagNodePosition,
} from "./tagGraphLayout"

export type TagGraphFileGroup = { file_id: number; label: string; tags: string[] }

export type FileClusterLayoutInput = {
  nodes: TagGraphNodeLike[]
  links: TagGraphLinkLike[]
  file_groups: TagGraphFileGroup[]
}

type Vec2 = { x: number; y: number }

function nodeKey(n: TagGraphNodeLike): string {
  return n.id || n.name
}

function intraFileLinks(tags: string[]): TagGraphLinkLike[] {
  const links: TagGraphLinkLike[] = []
  for (let i = 0; i < tags.length; i++) {
    for (let j = i + 1; j < tags.length; j++) {
      links.push({ source: tags[i], target: tags[j], value: 1 })
    }
  }
  return links
}

function normalizeLocalPositions(local: Map<string, Vec2>, maxRadius: number): Map<string, Vec2> {
  let maxR = 0
  for (const p of local.values()) maxR = Math.max(maxR, Math.hypot(p.x, p.y))
  const pad = 28
  const scale = maxR > 1e-4 ? (maxRadius - pad) / maxR : 1
  const out = new Map<string, Vec2>()
  for (const [k, p] of local) {
    out.set(k, { x: p.x * scale, y: p.y * scale })
  }
  return out
}

function gridCellCenter(index: number, total: number, plotW: number, plotH: number): Vec2 {
  if (total <= 1) return { x: 0, y: 0 }
  if (total === 2) {
    const offset = plotW * 0.22
    return index === 0 ? { x: -offset, y: 0 } : { x: offset, y: 0 }
  }
  const cols = Math.ceil(Math.sqrt(total))
  const rows = Math.ceil(total / cols)
  const col = index % cols
  const row = Math.floor(index / cols)
  const cellW = plotW / cols
  const cellH = plotH / rows
  const padX = cellW * 0.12
  const padY = cellH * 0.12
  return {
    x: -plotW / 2 + padX + cellW * (col + 0.5),
    y: -plotH / 2 + padY + cellH * (row + 0.5),
  }
}

function cellRadius(plotW: number, plotH: number, total: number, index: number): number {
  if (total <= 1) return Math.min(plotW, plotH) * 0.35
  if (total === 2) return Math.min(plotW * 0.38, plotH * 0.42)
  const cols = Math.ceil(Math.sqrt(total))
  const rows = Math.ceil(total / cols)
  return Math.min((plotW / cols) * 0.38, (plotH / rows) * 0.38)
}

function relaxSharedTags(
  accum: Map<string, { x: number; y: number; w: number }>,
  groups: TagGraphFileGroup[],
  plotW: number,
  plotH: number,
  total: number,
  rounds = 2,
) {
  const tagToFileIdxs = new Map<string, number[]>()
  groups.forEach((g, idx) => {
    for (const tag of g.tags) {
      const arr = tagToFileIdxs.get(tag) ?? []
      arr.push(idx)
      tagToFileIdxs.set(tag, arr)
    }
  })

  for (let r = 0; r < rounds; r++) {
    for (const [tag, indices] of tagToFileIdxs) {
      if (indices.length < 2) continue
      const cur = accum.get(tag)
      if (!cur) continue
      let tx = 0
      let ty = 0
      for (const idx of indices) {
        const c = gridCellCenter(idx, total, plotW, plotH)
        tx += c.x
        ty += c.y
      }
      tx /= indices.length
      ty /= indices.length
      const alpha = 0.12
      cur.x = cur.x * (1 - alpha) + tx * alpha
      cur.y = cur.y * (1 - alpha) + ty * alpha
    }
  }
}

/**
 * 每个 file_group 占网格一格；文件内 tag 力导向；多文件共享 tag 坐标加权平均并轻微松弛。
 */
export function packFileClusterPositions(
  data: FileClusterLayoutInput,
  plotW: number,
  plotH: number,
  symbolSizeFor: (fileCount: number) => number,
): Map<string, TagNodePosition> {
  const groups = data.file_groups.filter((g) => g.tags.length > 0)
  if (groups.length === 0) return new Map()

  const valueByKey = new Map<string, number>()
  for (const n of data.nodes) valueByKey.set(nodeKey(n), n.value)

  const accum = new Map<string, { x: number; y: number; w: number }>()
  const total = groups.length

  groups.forEach((group, idx) => {
    const tags = group.tags
    const local = layoutComponentForce(tags, intraFileLinks(tags))
    const maxR = cellRadius(plotW, plotH, total, idx)
    const scaled = normalizeLocalPositions(local, maxR)
    const center = gridCellCenter(idx, total, plotW, plotH)

    for (const tag of tags) {
      const p = scaled.get(tag) ?? { x: 0, y: 0 }
      const gx = center.x + p.x
      const gy = center.y + p.y
      const prev = accum.get(tag)
      if (prev) {
        prev.x += gx
        prev.y += gy
        prev.w += 1
      } else {
        accum.set(tag, { x: gx, y: gy, w: 1 })
      }
    }
  })

  relaxSharedTags(accum, groups, plotW, plotH, total)

  const out = new Map<string, TagNodePosition>()
  for (const [tag, { x, y, w }] of accum) {
    const fileCount = valueByKey.get(tag) ?? 1
    out.set(tag, {
      x: x / w,
      y: y / w,
      symbolSize: symbolSizeFor(fileCount),
    })
  }
  return out
}
