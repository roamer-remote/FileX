import type { Options } from 'vis-network'
import type { Network } from 'vis-network/standalone'
import type { WikiLinkGraphEdge, WikiLinkGraphNode, WikiLinkGraphResponse } from '@/api/knowledgeBase'
import { graphNodeVisRadius } from '@/lib/graphNodeSymbolSize'

const WIKI_TOPIC_KINDS = new Set(['entity', 'concept', 'synthesis'])

export type WikiEdgeType = WikiLinkGraphEdge['edge_type']

export type WikiGraphVisSizing = {
  singleBase: number
  displayRatio: number
  edgeLineWidth: number
}

export const DEFAULT_WIKI_GRAPH_SIZING: WikiGraphVisSizing = {
  singleBase: 48,
  displayRatio: 1,
  edgeLineWidth: 1,
}

export type VisWikiNodeMeta = {
  fileId: number
  name: string
  value: number
  pageKind: string
  wikiSlug: string | null
  isHub: boolean
}

export type VisWikiEdgeMeta = {
  edgeType: WikiEdgeType
  wikiSlug: string | null
}

const DIRECT_EDGE = {
  dark: { bg: 'rgba(48, 209, 88, 0.92)', border: 'rgba(48, 209, 88, 1)' },
  light: { bg: 'rgba(52, 199, 89, 0.92)', border: 'rgba(52, 199, 89, 1)' },
} as const

const COREF_EDGE = {
  dark: { color: 'rgba(180, 140, 255, 0.78)', highlight: 'rgba(200, 170, 255, 0.95)' },
  light: { color: 'rgba(120, 90, 200, 0.82)', highlight: 'rgba(100, 70, 180, 0.95)' },
} as const

const TOPIC_EDGE = {
  dark: { color: 'rgba(255, 180, 100, 0.55)', highlight: 'rgba(255, 200, 130, 0.85)' },
  light: { color: 'rgba(200, 130, 60, 0.55)', highlight: 'rgba(180, 110, 40, 0.85)' },
} as const

const HUB_NODE = {
  dark: { bg: 'rgba(255, 180, 100, 0.88)', border: 'rgba(255, 220, 160, 0.65)' },
  light: { bg: 'rgba(230, 150, 70, 0.92)', border: 'rgba(160, 90, 20, 0.45)' },
} as const

function fileNodeColors(accent: string, isDark: boolean) {
  return {
    background: accent,
    border: isDark ? 'rgba(255,255,255,0.28)' : 'rgba(0,0,0,0.12)',
    highlight: { background: '#ffffff', border: accent },
  }
}

function edgeVisStyle(edge: WikiLinkGraphEdge, isDark: boolean, edgeLineWidth: number) {
  const solidW = edgeLineWidth
  const topicW = Math.max(1, Math.round(edgeLineWidth * 0.75))
  if (edge.edge_type === 'wiki_coref') {
    const c = isDark ? COREF_EDGE.dark : COREF_EDGE.light
    return {
      dashes: false as const,
      width: solidW,
      color: { color: c.color, highlight: c.highlight, opacity: 0.85 },
    }
  }
  if (edge.edge_type === 'wiki_topic') {
    const c = isDark ? TOPIC_EDGE.dark : TOPIC_EDGE.light
    return {
      dashes: [4, 4] as number[],
      width: topicW,
      color: { color: c.color, highlight: c.highlight, opacity: 0.9 },
    }
  }
  const c = isDark ? DIRECT_EDGE.dark : DIRECT_EDGE.light
  return {
    dashes: false as const,
    width: solidW,
    color: { color: c.bg, highlight: c.border, opacity: 0.88 },
  }
}

/** vis.js 节点/边 — 对齐 graphify graph.html 的 size、physics 与边样式策略 */
export function buildVisWikiGraph(
  data: WikiLinkGraphResponse,
  isDark: boolean,
  accent: string,
  sizing: WikiGraphVisSizing = DEFAULT_WIKI_GRAPH_SIZING,
) {
  const maxValue = Math.max(1, ...data.nodes.map((n) => n.value))
  const ink = isDark ? '#f5f5f7' : '#1d1d1f'
  const { singleBase, displayRatio, edgeLineWidth } = sizing

  const nodeMeta = new Map<string, VisWikiNodeMeta>()
  const visNodes = data.nodes.map((n) => {
    const id = String(n.id)
    const isHub = WIKI_TOPIC_KINDS.has(n.page_kind)
    const radius = graphNodeVisRadius(n.value, singleBase, displayRatio)
    const size = isHub ? radius * 1.08 : radius
    const showLabel = n.value >= maxValue * 0.12 || data.nodes.length <= 40
    const hubColors = isDark ? HUB_NODE.dark : HUB_NODE.light
    const fileColors = fileNodeColors(accent, isDark)
    const meta: VisWikiNodeMeta = {
      fileId: n.id,
      name: n.name,
      value: n.value,
      pageKind: n.page_kind,
      wikiSlug: n.wiki_slug,
      isHub,
    }
    nodeMeta.set(id, meta)
    return {
      id,
      label: n.name,
      shape: isHub ? ('diamond' as const) : ('dot' as const),
      size,
      color: isHub
        ? {
            background: hubColors.bg,
            border: hubColors.border,
            highlight: { background: '#fff8ef', border: hubColors.border },
          }
        : fileColors,
      font: {
        size: showLabel ? 11 : 0,
        color: ink,
        strokeWidth: isDark ? 0 : 2,
        strokeColor: isDark ? undefined : '#ffffff',
      },
      title: n.name,
    }
  })

  const edgeMeta = new Map<number, VisWikiEdgeMeta>()
  const visEdges = data.links.map((l, i) => {
    const style = edgeVisStyle(l, isDark, edgeLineWidth)
    edgeMeta.set(i, { edgeType: l.edge_type, wikiSlug: l.wiki_slug ?? null })
    const slugHint = l.wiki_slug ? ` · ${l.wiki_slug}` : ''
    return {
      id: i,
      from: String(l.source),
      to: String(l.target),
      ...style,
      title: `${l.edge_type}${slugHint}`,
      arrows: { to: { enabled: l.edge_type === 'wiki_topic', scaleFactor: 0.45 } },
    }
  })

  return { visNodes, visEdges, nodeMeta, edgeMeta }
}

/** 稳定化后将全部节点居中并缩放进画布 */
export function fitWikiLinkNetwork(network: Network, container: HTMLElement, animate = true): void {
  const w = container.clientWidth
  const h = container.clientHeight
  if (w < 1 || h < 1) return
  network.setSize(`${w}px`, `${h}px`)
  network.fit({
    animation: animate
      ? { duration: 320, easingFunction: 'easeInOutQuad' }
      : false,
  })
}

/** graphify graph.html 同款 forceAtlas2Based 物理参数 */
export function wikiLinkNetworkOptions(): Options {
  return {
    physics: {
      enabled: true,
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {
        gravitationalConstant: -60,
        centralGravity: 0.005,
        springLength: 120,
        springConstant: 0.08,
        damping: 0.4,
        avoidOverlap: 0.8,
      },
      stabilization: { iterations: 200, fit: true },
    },
    interaction: {
      hover: true,
      tooltipDelay: 100,
      hideEdgesOnDrag: true,
      navigationButtons: false,
      keyboard: false,
      dragNodes: true,
      zoomView: true,
    },
    nodes: { borderWidth: 1.5 },
    edges: { smooth: { enabled: true, type: 'continuous', roundness: 0.2 }, selectionWidth: 3 },
  }
}

export function applyEdgeTypeFilter(
  edgeIds: number[],
  edgeMeta: Map<number, VisWikiEdgeMeta>,
  hidden: Set<WikiEdgeType>,
): { edgeId: number; hidden: boolean }[] {
  return edgeIds.map((id) => ({
    edgeId: id,
    hidden: hidden.has(edgeMeta.get(id)?.edgeType ?? 'file_direct'),
  }))
}

export function isWikiHubNode(n: WikiLinkGraphNode): boolean {
  return WIKI_TOPIC_KINDS.has(n.page_kind)
}
