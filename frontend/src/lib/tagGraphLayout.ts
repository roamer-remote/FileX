/** 标签共现图：连通分量检测与分区布局（关系网络图用） */

import { createSeededRandom } from "./seededRandom"

export type TagGraphNodeLike = { id: string; name: string; value: number }
export type TagGraphLinkLike = { source: string; target: string; value: number }

export type TagGraphLayoutInput = {
  nodes: TagGraphNodeLike[]
  links: TagGraphLinkLike[]
}

export type TagNodePosition = { x: number; y: number; symbolSize: number }

function nodeKey(n: TagGraphNodeLike): string {
  return n.id || n.name
}

/** 无向图连通分量；无边节点各自为 size=1 分量 */
export function findConnectedComponents(
  nodes: TagGraphNodeLike[],
  links: TagGraphLinkLike[],
): string[][] {
  const keys = nodes.map(nodeKey)
  const parent = new Map<string, string>()
  for (const k of keys) parent.set(k, k)

  const find = (x: string): string => {
    let p = parent.get(x)!
    while (p !== parent.get(p)) p = parent.get(p)!
    let cur = x
    while (cur !== p) {
      const next = parent.get(cur)!
      parent.set(cur, p)
      cur = next
    }
    return p
  }

  const union = (a: string, b: string) => {
    const ra = find(a)
    const rb = find(b)
    if (ra !== rb) parent.set(ra, rb)
  }

  const keySet = new Set(keys)
  for (const l of links) {
    if (keySet.has(l.source) && keySet.has(l.target)) union(l.source, l.target)
  }

  const buckets = new Map<string, string[]>()
  for (const k of keys) {
    const r = find(k)
    const arr = buckets.get(r) ?? []
    arr.push(k)
    buckets.set(r, arr)
  }

  return [...buckets.values()].sort((a, b) => b.length - a.length || a[0].localeCompare(b[0]))
}

export function countConnectedComponents(nodes: TagGraphNodeLike[], links: TagGraphLinkLike[]): number {
  return findConnectedComponents(nodes, links).length
}

type Vec2 = { x: number; y: number }

function forceParamsForComponent(size: number) {
  const n = Math.max(1, size)
  return {
    repulsion: Math.max(120, Math.min(480, 80 + n * 18)),
    edgeLength: Math.max(36, Math.min(100, 72 - n * 0.5)),
    iterations: Math.min(60, 28 + n * 4),
  }
}

/** 单分量轻量力导向；单节点返回原点 */
export function layoutComponentForce(
  memberKeys: string[],
  links: TagGraphLinkLike[],
  iterations?: number,
): Map<string, Vec2> {
  const out = new Map<string, Vec2>()
  if (memberKeys.length === 0) return out
  if (memberKeys.length === 1) {
    out.set(memberKeys[0], { x: 0, y: 0 })
    return out
  }

  const memberSet = new Set(memberKeys)
  const internalLinks = links.filter((l) => memberSet.has(l.source) && memberSet.has(l.target))
  const { repulsion, edgeLength, iterations: defaultIter } = forceParamsForComponent(memberKeys.length)
  const iters = iterations ?? defaultIter

  const seedKey = [...memberKeys].sort().join("\0")
  const rand = createSeededRandom(`tag-force:${seedKey}`)
  const pos = new Map<string, Vec2>()
  const spread = 24 + memberKeys.length * 8
  for (const k of memberKeys) {
    pos.set(k, {
      x: (rand() - 0.5) * spread * 2,
      y: (rand() - 0.5) * spread * 2,
    })
  }

  for (let step = 0; step < iters; step++) {
    const disp = new Map<string, Vec2>()
    for (const k of memberKeys) disp.set(k, { x: 0, y: 0 })

    for (let i = 0; i < memberKeys.length; i++) {
      for (let j = i + 1; j < memberKeys.length; j++) {
        const a = memberKeys[i]
        const b = memberKeys[j]
        const pa = pos.get(a)!
        const pb = pos.get(b)!
        let dx = pa.x - pb.x
        let dy = pa.y - pb.y
        let dist = Math.hypot(dx, dy)
        if (dist < 1e-4) {
          dx = (rand() - 0.5) * 0.01
          dy = (rand() - 0.5) * 0.01
          dist = Math.hypot(dx, dy)
        }
        const force = (repulsion * repulsion) / dist
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        disp.get(a)!.x += fx
        disp.get(a)!.y += fy
        disp.get(b)!.x -= fx
        disp.get(b)!.y -= fy
      }
    }

    for (const l of internalLinks) {
      const pa = pos.get(l.source)
      const pb = pos.get(l.target)
      if (!pa || !pb) continue
      let dx = pb.x - pa.x
      let dy = pb.y - pa.y
      let dist = Math.hypot(dx, dy)
      if (dist < 1e-4) {
        dx = (rand() - 0.5) * 0.01
        dy = (rand() - 0.5) * 0.01
        dist = Math.hypot(dx, dy)
      }
      const force = (dist - edgeLength) * 0.12
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      disp.get(l.source)!.x += fx
      disp.get(l.source)!.y += fy
      disp.get(l.target)!.x -= fx
      disp.get(l.target)!.y -= fy
    }

    for (const k of memberKeys) {
      const p = pos.get(k)!
      const d = disp.get(k)!
      p.x += d.x * 0.08
      p.y += d.y * 0.08
    }
  }

  for (const k of memberKeys) out.set(k, pos.get(k)!)
  return out
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

/**
 * 多连通分量时：各分量落入独立网格区域；返回全图节点坐标（数据坐标，与 ECharts graph layout:none 一致）。
 */
export function packComponentPositions(
  data: TagGraphLayoutInput,
  plotW: number,
  plotH: number,
  symbolSizeFor: (fileCount: number) => number,
): Map<string, TagNodePosition> {
  const components = findConnectedComponents(data.nodes, data.links)
  const valueByKey = new Map<string, number>()
  for (const n of data.nodes) valueByKey.set(nodeKey(n), n.value)

  const out = new Map<string, TagNodePosition>()
  const total = components.length

  components.forEach((members, idx) => {
    const local = layoutComponentForce(members, data.links)
    const maxR = cellRadius(plotW, plotH, total, idx)
    const scaled = normalizeLocalPositions(local, maxR)
    const center = gridCellCenter(idx, total, plotW, plotH)

    for (const k of members) {
      const p = scaled.get(k) ?? { x: 0, y: 0 }
      const fileCount = valueByKey.get(k) ?? 1
      out.set(k, {
        x: center.x + p.x,
        y: center.y + p.y,
        symbolSize: symbolSizeFor(fileCount),
      })
    }
  })

  return out
}
