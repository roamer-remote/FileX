import type { TagGraphLink, TagGraphNode, TagGraphResponse } from '@/api/files'
import { graphNodeVisRadius } from '@/lib/graphNodeSymbolSize'
import {
  fitWikiLinkNetwork,
  wikiLinkNetworkOptions,
  type WikiGraphVisSizing,
} from '@/lib/wikiLinkVisGraph'

export type TagGraphVisSizing = WikiGraphVisSizing

export type VisTagNodeMeta = {
  name: string
  value: number
}

function tagNodeColors(value: number, minV: number, maxV: number, isDark: boolean) {
  const span = Math.max(maxV - minV, 1)
  const u = (value - minV) / span
  const h = 168 + u * 148
  return {
    background: `hsla(${h}, ${isDark ? 88 : 90}%, ${isDark ? 56 : 48}%, ${isDark ? 0.92 : 0.95})`,
    border: `hsla(${h}, 82%, ${isDark ? 74 : 36}%, ${isDark ? 0.38 : 0.28})`,
    highlight: {
      background: `hsla(${h}, 95%, ${isDark ? 68 : 54}%, 1)`,
      border: `hsla(${h}, 94%, 62%, ${isDark ? 0.75 : 0.52})`,
    },
  }
}

function edgeVisStyle(isDark: boolean, edgeLineWidth: number) {
  const color = isDark ? 'rgba(140, 200, 255, 0.55)' : 'rgba(100, 175, 230, 0.62)'
  const highlight = isDark ? 'rgba(48, 209, 88, 0.88)' : 'rgba(52, 199, 89, 0.92)'
  return {
    width: edgeLineWidth,
    color: { color, highlight, opacity: isDark ? 0.55 : 0.62 },
  }
}

function nodeKey(n: TagGraphNode): string {
  return n.id || n.name
}

/** vis.js 标签共现图 — 与资料关系图同款 forceAtlas2Based 物理与 fit 策略 */
export function buildVisTagGraph(
  data: TagGraphResponse,
  isDark: boolean,
  sizing: TagGraphVisSizing,
) {
  const counts = data.nodes.map((n) => n.value)
  const minV = counts.length ? Math.min(...counts) : 0
  const maxV = counts.length ? Math.max(...counts) : 1
  const maxValue = Math.max(1, maxV)
  const ink = isDark ? '#f5f5f7' : '#1d1d1f'
  const { singleBase, displayRatio, edgeLineWidth } = sizing

  const nodeMeta = new Map<string, VisTagNodeMeta>()
  const visNodes = data.nodes.map((n) => {
    const id = nodeKey(n)
    const radius = graphNodeVisRadius(n.value, singleBase, displayRatio)
    const showLabel = n.value >= maxValue * 0.12 || data.nodes.length <= 40
    const colors = tagNodeColors(n.value, minV, maxV, isDark)
    nodeMeta.set(id, { name: n.name, value: n.value })
    return {
      id,
      label: n.name,
      shape: 'dot' as const,
      size: radius,
      color: colors,
      font: {
        size: showLabel ? 11 : 0,
        color: ink,
        strokeWidth: isDark ? 0 : 2,
        strokeColor: isDark ? undefined : '#ffffff',
      },
      title: `${n.name} · ${n.value}`,
    }
  })

  const edgeMeta = new Map<number, TagGraphLink>()
  const visEdges = data.links.map((l, i) => {
    const style = edgeVisStyle(isDark, edgeLineWidth)
    edgeMeta.set(i, l)
    return {
      id: i,
      from: l.source,
      to: l.target,
      ...style,
      title: `${l.source} × ${l.target} · ${l.value}`,
    }
  })

  return { visNodes, visEdges, nodeMeta, edgeMeta }
}

export { fitWikiLinkNetwork as fitTagGraphNetwork, wikiLinkNetworkOptions as tagGraphNetworkOptions }
