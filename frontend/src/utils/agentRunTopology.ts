import type { AgentRunEvent } from '@/api/agentRuns'

export type AgentTopologyNode = {
  id: string
  label: string
  layer: 'router' | 'kb'
}

export type AgentTopologyEdge = {
  source: string
  target: string
}

export type DisplayTopologyNode = {
  id: string
  templateId: string
  label: string
  layer: 'router' | 'kb'
  taskKey?: string
}

export type AgentRunViewMode = 'kb_full' | 'router_only'

export const AGENT_RUN_TOPOLOGY_NODES: AgentTopologyNode[] = [
  { id: 'classify', label: '理解意图', layer: 'router' },
  { id: 'preflight_global', label: '验证权限', layer: 'router' },
  { id: 'kb_search_branch', label: '进入资料库', layer: 'router' },
  { id: 'preflight', label: '准备检索', layer: 'kb' },
  { id: 'classify_query', label: '分析问句', layer: 'kb' },
  { id: 'initial_search', label: '检索资料库', layer: 'kb' },
  { id: 'assess', label: '评估证据', layer: 'kb' },
  { id: 'get_md_worker', label: '阅读文档', layer: 'kb' },
  { id: 'wiki_expand', label: '扩展 Wiki', layer: 'kb' },
  { id: 'verify_evidence', label: '核对证据', layer: 'kb' },
  { id: 'synthesize', label: '生成回答', layer: 'kb' },
]

export const AGENT_RUN_ROUTER_EXTENSION_NODES: AgentTopologyNode[] = [
  { id: 'emit_hint', label: '分发子流程', layer: 'router' },
  { id: 'confirm_external', label: '确认扩外网', layer: 'router' },
  { id: 'auth_error', label: '鉴权失败', layer: 'router' },
]

export const AGENT_RUN_TOPOLOGY_EDGES: AgentTopologyEdge[] = [
  { source: 'classify', target: 'preflight_global' },
  { source: 'preflight_global', target: 'kb_search_branch' },
  { source: 'kb_search_branch', target: 'preflight' },
  { source: 'preflight', target: 'classify_query' },
  { source: 'classify_query', target: 'initial_search' },
  { source: 'initial_search', target: 'assess' },
  { source: 'assess', target: 'get_md_worker' },
  { source: 'assess', target: 'wiki_expand' },
  { source: 'get_md_worker', target: 'verify_evidence' },
  { source: 'wiki_expand', target: 'verify_evidence' },
  { source: 'assess', target: 'verify_evidence' },
  { source: 'verify_evidence', target: 'synthesize' },
]

export const AGENT_RUN_ROUTER_EXTENSION_EDGES: AgentTopologyEdge[] = [
  { source: 'classify', target: 'emit_hint' },
  { source: 'preflight_global', target: 'emit_hint' },
  { source: 'preflight_global', target: 'auth_error' },
  { source: 'kb_search_branch', target: 'emit_hint' },
  { source: 'kb_search_branch', target: 'confirm_external' },
]

const NODE_ALIAS: Record<string, string> = {
  preflight: 'preflight',
  struct_relation_probe: 'initial_search',
  initial_search: 'initial_search',
  assess: 'assess',
  react_plan: 'assess',
  react_search: 'initial_search',
  monte_carlo: 'initial_search',
  get_md_worker: 'get_md_worker',
  wiki_expand: 'wiki_expand',
  verify_evidence: 'verify_evidence',
  synthesize: 'synthesize',
  preflight_global: 'preflight_global',
  kb_search_branch: 'kb_search_branch',
  emit_hint: 'emit_hint',
  confirm_external: 'confirm_external',
  auth_error: 'auth_error',
}

export function mapEventNodeToTopology(nodeId: string): string {
  return NODE_ALIAS[nodeId] ?? nodeId
}

export function resolveAgentRunViewMode(events: AgentRunEvent[]): AgentRunViewMode {
  if (events.some((ev) => ev.layer === 'kb')) return 'kb_full'
  return 'router_only'
}

export function workerGraphId(taskKey: string): string {
  return `get_md_worker::${taskKey}`
}

function workerLabelFromTaskKey(taskKey: string): string {
  const match = taskKey.match(/^get_md:file_id=(\d+)$/)
  if (match) return `阅读文档 #${match[1]}`
  return taskKey
}

export function collectGetMdWorkerTaskKeys(events: AgentRunEvent[]): string[] {
  const keys: string[] = []
  const seen = new Set<string>()
  for (const ev of events) {
    if (mapEventNodeToTopology(ev.node_id) !== 'get_md_worker') continue
    const taskKey = ev.task_key?.trim()
    if (!taskKey || seen.has(taskKey)) continue
    seen.add(taskKey)
    keys.push(taskKey)
  }
  return keys
}

function routerOnlyTopology(): {
  nodes: DisplayTopologyNode[]
  edges: AgentTopologyEdge[]
} {
  const merged = [...AGENT_RUN_TOPOLOGY_NODES.filter((n) => n.layer === 'router'), ...AGENT_RUN_ROUTER_EXTENSION_NODES]
  const seen = new Set<string>()
  const nodes: DisplayTopologyNode[] = []
  for (const node of merged) {
    if (seen.has(node.id)) continue
    seen.add(node.id)
    nodes.push({
      id: node.id,
      templateId: node.id,
      label: node.label,
      layer: node.layer,
    })
  }
  const nodeIds = new Set(nodes.map((n) => n.id))
  const edges = [
    ...AGENT_RUN_TOPOLOGY_EDGES.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target)),
    ...AGENT_RUN_ROUTER_EXTENSION_EDGES.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target)),
  ]
  return { nodes, edges }
}

function remapWorkerEdges(
  edges: AgentTopologyEdge[],
  workerKeys: string[],
): AgentTopologyEdge[] {
  const out: AgentTopologyEdge[] = []
  for (const edge of edges) {
    if (edge.target === 'get_md_worker') {
      for (const taskKey of workerKeys) {
        out.push({ source: edge.source, target: workerGraphId(taskKey) })
      }
      continue
    }
    if (edge.source === 'get_md_worker') {
      for (const taskKey of workerKeys) {
        out.push({ source: workerGraphId(taskKey), target: edge.target })
      }
      continue
    }
    out.push(edge)
  }
  return out
}

export function buildDisplayTopology(
  events: AgentRunEvent[],
  viewMode: AgentRunViewMode,
): { nodes: DisplayTopologyNode[]; edges: AgentTopologyEdge[] } {
  if (viewMode === 'router_only') {
    return routerOnlyTopology()
  }

  const workerKeys = collectGetMdWorkerTaskKeys(events)
  if (workerKeys.length <= 1) {
    return {
      nodes: AGENT_RUN_TOPOLOGY_NODES.map((node) => ({
        id: node.id,
        templateId: node.id,
        label: node.label,
        layer: node.layer,
        taskKey: node.id === 'get_md_worker' ? workerKeys[0] : undefined,
      })),
      edges: [...AGENT_RUN_TOPOLOGY_EDGES],
    }
  }

  const nodes: DisplayTopologyNode[] = AGENT_RUN_TOPOLOGY_NODES.filter(
    (node) => node.id !== 'get_md_worker',
  ).map((node) => ({
    id: node.id,
    templateId: node.id,
    label: node.label,
    layer: node.layer,
  }))

  for (const taskKey of workerKeys) {
    nodes.push({
      id: workerGraphId(taskKey),
      templateId: 'get_md_worker',
      label: workerLabelFromTaskKey(taskKey),
      layer: 'kb',
      taskKey,
    })
  }

  return {
    nodes,
    edges: remapWorkerEdges(AGENT_RUN_TOPOLOGY_EDGES, workerKeys),
  }
}

export type NodeVisualState = 'idle' | 'active' | 'done' | 'error'

function resolveEventTargetNodeIds(
  ev: AgentRunEvent,
  nodes: DisplayTopologyNode[],
): string[] {
  const templateId = mapEventNodeToTopology(ev.node_id)
  if (templateId === 'get_md_worker' && ev.task_key?.trim()) {
    const graphId = workerGraphId(ev.task_key.trim())
    if (nodes.some((n) => n.id === graphId)) return [graphId]
  }
  return nodes.filter((n) => n.templateId === templateId).map((n) => n.id)
}

export function deriveNodeStates(
  events: AgentRunEvent[],
  running: boolean,
  nodes: DisplayTopologyNode[],
): Record<string, NodeVisualState> {
  const states: Record<string, NodeVisualState> = {}
  for (const node of nodes) {
    states[node.id] = 'idle'
  }
  for (const ev of events) {
    for (const nodeId of resolveEventTargetNodeIds(ev, nodes)) {
      if (!states[nodeId]) continue
      if (ev.phase === 'error') states[nodeId] = 'error'
      else if (ev.phase === 'end' || ev.phase === 'skip') states[nodeId] = 'done'
      else if (ev.phase === 'start') states[nodeId] = running ? 'active' : 'done'
    }
  }
  return states
}

export function activeEdgeKeys(
  events: AgentRunEvent[],
  running: boolean,
  edges: AgentTopologyEdge[],
  nodes: DisplayTopologyNode[],
): Set<string> {
  const out = new Set<string>()
  if (!running || events.length === 0) return out
  const last = events[events.length - 1]
  const fromIds = resolveEventTargetNodeIds(last, nodes)
  const fromId = fromIds[0]
  if (!fromId) return out
  for (const edge of edges) {
    if (edge.source === fromId) out.add(`${edge.source}->${edge.target}`)
  }
  return out
}

export type ModuleHintSummary = {
  intent?: string
  module_ids?: string[]
  reason?: string
  next_action?: string
  execution_mode?: string
}

export function extractModuleHints(
  summaryJson: Record<string, unknown> | null | undefined,
): ModuleHintSummary[] {
  const raw = summaryJson?.module_hints
  if (!Array.isArray(raw)) return []
  const out: ModuleHintSummary[] = []
  for (const row of raw) {
    if (!row || typeof row !== 'object') continue
    const hint = row as Record<string, unknown>
    out.push({
      intent: typeof hint.intent === 'string' ? hint.intent : undefined,
      module_ids: Array.isArray(hint.module_ids)
        ? hint.module_ids.filter((id): id is string => typeof id === 'string')
        : undefined,
      reason: typeof hint.reason === 'string' ? hint.reason : undefined,
      next_action: typeof hint.next_action === 'string' ? hint.next_action : undefined,
      execution_mode: typeof hint.execution_mode === 'string' ? hint.execution_mode : undefined,
    })
  }
  return out
}
