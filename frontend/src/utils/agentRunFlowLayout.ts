import type { DisplayTopologyNode } from '@/utils/agentRunTopology'

export type FlowNodePlacement = {
  left: number
  top: number
  width: number
  height: number
  lane: 'L1' | 'L2'
  wide?: boolean
}

export const FLOW_NODE_WIDTH = 146
export const FLOW_NODE_HEIGHT = 96
export const FLOW_WIDE_NODE_WIDTH = 214
export const FLOW_WIDE_NODE_HEIGHT = 150
export const FLOW_NODE_GAP = 36
export const FLOW_CANVAS_PADDING = 48
export const FLOW_MIN_CANVAS_WIDTH = 720
export const FLOW_MIN_CANVAS_HEIGHT = 420

const L1_TEMPLATE_PLACEMENTS: Record<string, FlowNodePlacement> = {
  classify: { left: 90, top: 82, width: FLOW_NODE_WIDTH, height: FLOW_NODE_HEIGHT, lane: 'L1' },
  preflight_global: { left: 292, top: 82, width: FLOW_NODE_WIDTH, height: FLOW_NODE_HEIGHT, lane: 'L1' },
  kb_search_branch: { left: 494, top: 82, width: FLOW_NODE_WIDTH, height: FLOW_NODE_HEIGHT, lane: 'L1' },
}

const ROUTER_L2_TEMPLATE_PLACEMENTS: Record<string, FlowNodePlacement> = {
  emit_hint: { left: 292, top: 280, width: FLOW_NODE_WIDTH, height: FLOW_NODE_HEIGHT, lane: 'L2' },
  confirm_external: { left: 494, top: 280, width: FLOW_NODE_WIDTH, height: FLOW_NODE_HEIGHT, lane: 'L2' },
  auth_error: { left: 494, top: 426, width: FLOW_NODE_WIDTH, height: FLOW_NODE_HEIGHT, lane: 'L2' },
}

const WORKER_ROW_GAP = 40
const WORKER_STACK_GAP = 24

function standardNode(left: number, top: number, lane: 'L1' | 'L2'): FlowNodePlacement {
  return { left, top, width: FLOW_NODE_WIDTH, height: FLOW_NODE_HEIGHT, lane }
}

function workerNode(left: number, top: number): FlowNodePlacement {
  return {
    left,
    top,
    width: FLOW_WIDE_NODE_WIDTH,
    height: FLOW_WIDE_NODE_HEIGHT,
    lane: 'L2',
    wide: true,
  }
}

export function fallbackFlowPlacement(
  index: number,
  layer: DisplayTopologyNode['layer'],
): FlowNodePlacement {
  return {
    left: 90 + (index % 6) * (FLOW_NODE_WIDTH + FLOW_NODE_GAP),
    top: layer === 'router' ? 82 : 280 + Math.floor(index / 6) * 146,
    width: FLOW_NODE_WIDTH,
    height: FLOW_NODE_HEIGHT,
    lane: layer === 'router' ? 'L1' : 'L2',
  }
}

export function computeRouterPlacements(nodes: DisplayTopologyNode[]): Map<string, FlowNodePlacement> {
  const placements = new Map<string, FlowNodePlacement>()
  for (const node of nodes) {
    const fixed =
      L1_TEMPLATE_PLACEMENTS[node.templateId] ??
      ROUTER_L2_TEMPLATE_PLACEMENTS[node.templateId]
    placements.set(node.id, fixed ?? fallbackFlowPlacement(placements.size, node.layer))
  }
  return placements
}

export function computeKbFullPlacements(nodes: DisplayTopologyNode[]): Map<string, FlowNodePlacement> {
  const placements = new Map<string, FlowNodePlacement>()
  const workers = nodes.filter((node) => node.templateId === 'get_md_worker')

  for (const templateId of ['classify', 'preflight_global', 'kb_search_branch'] as const) {
    const node = nodes.find((item) => item.templateId === templateId)
    if (!node) continue
    placements.set(node.id, L1_TEMPLATE_PLACEMENTS[templateId])
  }

  let x = 90
  const rowY = 280
  let assessLeft = 0
  for (const templateId of ['preflight', 'classify_query', 'initial_search', 'assess'] as const) {
    const node = nodes.find((item) => item.templateId === templateId)
    if (!node) continue
    if (templateId === 'assess') assessLeft = x
    placements.set(node.id, standardNode(x, rowY, 'L2'))
    x += FLOW_NODE_WIDTH + FLOW_NODE_GAP
  }

  const wiki = nodes.find((node) => node.templateId === 'wiki_expand')
  if (wiki) {
    placements.set(wiki.id, standardNode(x, rowY, 'L2'))
    x += FLOW_NODE_WIDTH + FLOW_NODE_GAP
  }

  const verify = nodes.find((node) => node.templateId === 'verify_evidence')
  const synthesize = nodes.find((node) => node.templateId === 'synthesize')
  const tailX = x
  if (verify) {
    placements.set(verify.id, standardNode(tailX, 420, 'L2'))
  }
  if (synthesize) {
    placements.set(synthesize.id, standardNode(tailX, 560, 'L2'))
  }

  if (workers.length > 0) {
    const workerRowY = rowY + FLOW_NODE_HEIGHT + WORKER_ROW_GAP
    workers.forEach((worker, index) => {
      placements.set(
        worker.id,
        workerNode(
          assessLeft,
          workerRowY + index * (FLOW_WIDE_NODE_HEIGHT + WORKER_STACK_GAP),
        ),
      )
    })
  }

  for (const node of nodes) {
    if (placements.has(node.id)) continue
    placements.set(node.id, fallbackFlowPlacement(placements.size, node.layer))
  }

  return placements
}

export function computeFlowPlacements(
  nodes: DisplayTopologyNode[],
  viewMode: 'kb_full' | 'router_only',
): Map<string, FlowNodePlacement> {
  if (viewMode === 'kb_full') {
    return computeKbFullPlacements(nodes)
  }
  return computeRouterPlacements(nodes)
}

export function computeCanvasBounds(
  placements: Iterable<FlowNodePlacement>,
  padding = FLOW_CANVAS_PADDING,
): { width: number; height: number } {
  let maxRight = 0
  let maxBottom = 0
  for (const placement of placements) {
    maxRight = Math.max(maxRight, placement.left + placement.width)
    maxBottom = Math.max(maxBottom, placement.top + placement.height)
  }
  return {
    width: Math.max(FLOW_MIN_CANVAS_WIDTH, maxRight + padding),
    height: Math.max(FLOW_MIN_CANVAS_HEIGHT, maxBottom + padding),
  }
}
