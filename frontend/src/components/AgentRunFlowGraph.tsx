import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { AgentRunEvent } from '@/api/agentRuns'
import {
  computeCanvasBounds,
  computeFlowPlacements,
  type FlowNodePlacement,
} from '@/utils/agentRunFlowLayout'
import { computeEdgePolyline } from '@/utils/agentRunFlowEdges'
import {
  activeEdgeKeys,
  buildDisplayTopology,
  deriveNodeStates,
  mapEventNodeToTopology,
  type DisplayTopologyNode,
  type NodeVisualState,
  resolveAgentRunViewMode,
} from '@/utils/agentRunTopology'
import './AgentRunFlowGraph.css'

type Props = {
  events: AgentRunEvent[]
  running?: boolean
}

type PositionedNode = DisplayTopologyNode & {
  placement: FlowNodePlacement
  state: NodeVisualState
  latestEvent?: AgentRunEvent
}

const TEMPLATE_LABEL_KEYS: Record<string, string> = {
  classify: 'agentRuns.flowGraph.labels.classify',
  preflight_global: 'agentRuns.flowGraph.labels.preflightGlobal',
  kb_search_branch: 'agentRuns.flowGraph.labels.kbSearchBranch',
  preflight: 'agentRuns.flowGraph.labels.preflight',
  classify_query: 'agentRuns.flowGraph.labels.classifyQuery',
  initial_search: 'agentRuns.flowGraph.labels.initialSearch',
  assess: 'agentRuns.flowGraph.labels.assess',
  get_md_worker: 'agentRuns.flowGraph.labels.getMdWorker',
  wiki_expand: 'agentRuns.flowGraph.labels.wikiExpand',
  verify_evidence: 'agentRuns.flowGraph.labels.verifyEvidence',
  synthesize: 'agentRuns.flowGraph.labels.synthesize',
  emit_hint: 'agentRuns.flowGraph.labels.emitHint',
  confirm_external: 'agentRuns.flowGraph.labels.confirmExternal',
  auth_error: 'agentRuns.flowGraph.labels.authError',
}

function displayLabel(node: DisplayTopologyNode, t: (key: string) => string): string {
  const key = TEMPLATE_LABEL_KEYS[node.templateId]
  if (key) return t(key)
  return node.label
}

function compactTime(ts?: string): string | undefined {
  if (!ts) return undefined
  const match = ts.match(/T(\d{2}:\d{2}:\d{2})/)
  if (match) return match[1]
  return ts
}

function durationText(ms?: number | null): string | undefined {
  if (ms == null) return undefined
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(2).replace(/\.?0+$/, '')}s`
}

function eventMatchesNode(ev: AgentRunEvent, node: DisplayTopologyNode): boolean {
  if (node.templateId === 'get_md_worker') {
    return mapEventNodeToTopology(ev.node_id) === 'get_md_worker' && ev.task_key === node.taskKey
  }
  return mapEventNodeToTopology(ev.node_id) === node.templateId
}

function latestEventForNode(events: AgentRunEvent[], node: DisplayTopologyNode): AgentRunEvent | undefined {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i]
    if (eventMatchesNode(ev, node)) return ev
  }
  return undefined
}

export default function AgentRunFlowGraph({ events, running = false }: Props) {
  const { t } = useTranslation()
  const viewMode = useMemo(() => resolveAgentRunViewMode(events), [events])
  const topology = useMemo(
    () => buildDisplayTopology(events, viewMode),
    [events, viewMode],
  )
  const nodeStates = useMemo(
    () => deriveNodeStates(events, running, topology.nodes),
    [events, running, topology.nodes],
  )
  const edgesActive = useMemo(
    () => activeEdgeKeys(events, running, topology.edges, topology.nodes),
    [events, running, topology.edges, topology.nodes],
  )

  const flowPlacements = useMemo(
    () => computeFlowPlacements(topology.nodes, viewMode),
    [topology.nodes, viewMode],
  )

  const positionedNodes = useMemo<PositionedNode[]>(() => {
    return topology.nodes.map((node) => ({
      ...node,
      placement: flowPlacements.get(node.id) ?? {
        left: 0,
        top: 0,
        width: 146,
        height: 96,
        lane: node.layer === 'router' ? 'L1' : 'L2',
      },
      state: nodeStates[node.id] ?? 'idle',
      latestEvent: latestEventForNode(events, node),
    }))
  }, [events, flowPlacements, nodeStates, topology.nodes])

  const canvasBounds = useMemo(
    () => computeCanvasBounds(positionedNodes.map((node) => node.placement)),
    [positionedNodes],
  )

  const nodesById = useMemo(
    () => new Map(positionedNodes.map((node) => [node.id, node])),
    [positionedNodes],
  )

  const flowObstacles = useMemo(
    () => positionedNodes.map((node) => ({ id: node.id, placement: node.placement })),
    [positionedNodes],
  )

  const edgePathFor = useCallback(
    (source: PositionedNode, target: PositionedNode) =>
      computeEdgePolyline(source.placement, target.placement, {
        sourceId: source.id,
        targetId: target.id,
        obstacles: flowObstacles,
      }),
    [flowObstacles],
  )

  return (
    <div className="agent-run-flow" aria-live="polite">
      <div
        className="agent-run-flow__trace-canvas"
        style={{ width: canvasBounds.width, height: canvasBounds.height }}
      >
        <div className="agent-run-flow__caption">{t('agentRuns.flowGraph.caption')}</div>
        <div className="agent-run-flow__lane" data-lane="L1">L1</div>
        <div className="agent-run-flow__lane agent-run-flow__lane--l2" data-lane="L2">L2</div>
        <svg
          className="agent-run-flow__svg"
          width={canvasBounds.width}
          height={canvasBounds.height}
          viewBox={`0 0 ${canvasBounds.width} ${canvasBounds.height}`}
          aria-hidden
        >
          <defs>
            <marker
              id="agent-run-flow-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="12"
              markerHeight="12"
              markerUnits="userSpaceOnUse"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" />
            </marker>
            <marker
              id="agent-run-flow-arrow-blue"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="12"
              markerHeight="12"
              markerUnits="userSpaceOnUse"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" />
            </marker>
          </defs>
          {topology.edges.map((edge) => {
            const source = nodesById.get(edge.source)
            const target = nodesById.get(edge.target)
            if (!source || !target) return null
            const key = `${edge.source}->${edge.target}`
            const active = edgesActive.has(key)
            const toSynthesize = edge.target === 'synthesize'
            return (
              <g key={key}>
                <path
                  className={
                    'agent-run-flow__flow-path' +
                    (active ? ' agent-run-flow__flow-path--active' : '') +
                    (toSynthesize ? ' agent-run-flow__flow-path--output' : '')
                  }
                  markerEnd={toSynthesize ? 'url(#agent-run-flow-arrow-blue)' : 'url(#agent-run-flow-arrow)'}
                  d={edgePathFor(source, target)}
                />
                {active ? (
                  <path className="agent-run-flow__flow-pulse" d={edgePathFor(source, target)} />
                ) : null}
              </g>
            )
          })}
        </svg>

        {positionedNodes.map((node) => {
          const time = compactTime(node.latestEvent?.ts)
          const duration = durationText(node.latestEvent?.duration_ms)
          return (
            <article
              key={node.id}
              className={
                'agent-run-flow__node-card' +
                (node.placement.wide ? ' agent-run-flow__node-card--wide' : '') +
                (node.state === 'active' ? ' agent-run-flow__node-card--active' : '') +
                (node.state === 'done' ? ' agent-run-flow__node-card--done' : '') +
                (node.state === 'error' ? ' agent-run-flow__node-card--error' : '') +
                (node.templateId === 'synthesize' ? ' agent-run-flow__node-card--output' : '')
              }
              style={{
                left: node.placement.left,
                top: node.placement.top,
                width: node.placement.width,
                height: node.placement.height,
              }}
            >
              <div className="agent-run-flow__node-title">
                <span className="agent-run-flow__state-icon" aria-hidden>
                  {node.state === 'active' || node.state === 'idle' ? '' : '✓'}
                </span>
                <span>{displayLabel(node, t)}</span>
              </div>
              {node.templateId === 'get_md_worker' && node.taskKey ? (
                <div className="agent-run-flow__task-key">{node.taskKey}</div>
              ) : null}
              <div className="agent-run-flow__node-meta">
                <span>{time ?? t(`agentRuns.flowGraph.status.${node.state}`)}</span>
                {duration ? <span>{duration}</span> : null}
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}
