import { describe, expect, it } from 'vitest'
import type { AgentRunEvent } from '@/api/agentRuns'
import {
  activeEdgeKeys,
  buildDisplayTopology,
  collectGetMdWorkerTaskKeys,
  deriveNodeStates,
  extractModuleHints,
  mapEventNodeToTopology,
  resolveAgentRunViewMode,
  workerGraphId,
} from './agentRunTopology'

function ev(partial: Partial<AgentRunEvent> & Pick<AgentRunEvent, 'seq' | 'node_id' | 'phase'>): AgentRunEvent {
  return {
    attempt: 1,
    ts: '2026-07-03T00:00:00+08:00',
    layer: partial.layer ?? 'kb',
    label: partial.label ?? partial.node_id,
    ...partial,
  }
}

describe('agentRunTopology', () => {
  it('keeps router classify separate from kb classify_query', () => {
    expect(mapEventNodeToTopology('classify')).toBe('classify')
    expect(mapEventNodeToTopology('classify_query')).toBe('classify_query')
  })

  it('maps kb preflight and router preflight_global independently', () => {
    expect(mapEventNodeToTopology('preflight')).toBe('preflight')
    expect(mapEventNodeToTopology('preflight_global')).toBe('preflight_global')
  })

  it('aliases struct_relation_probe to initial_search', () => {
    expect(mapEventNodeToTopology('struct_relation_probe')).toBe('initial_search')
  })

  it('detects router-only view when no kb layer events exist', () => {
    const events = [
      ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'start' }),
      ev({ seq: 2, layer: 'router', node_id: 'emit_hint', phase: 'end' }),
    ]
    expect(resolveAgentRunViewMode(events)).toBe('router_only')
    const topo = buildDisplayTopology(events, 'router_only')
    expect(topo.nodes.some((n) => n.layer === 'kb')).toBe(false)
    expect(topo.nodes.some((n) => n.id === 'emit_hint')).toBe(true)
  })

  it('expands parallel get_md_worker nodes by task_key', () => {
    const events = [
      ev({
        seq: 1,
        node_id: 'get_md_worker',
        phase: 'start',
        task_key: 'get_md:file_id=7',
      }),
      ev({
        seq: 2,
        node_id: 'get_md_worker',
        phase: 'start',
        task_key: 'get_md:file_id=9',
      }),
    ]
    expect(collectGetMdWorkerTaskKeys(events)).toEqual(['get_md:file_id=7', 'get_md:file_id=9'])
    const topo = buildDisplayTopology(events, 'kb_full')
    expect(topo.nodes.filter((n) => n.templateId === 'get_md_worker')).toHaveLength(2)
    expect(topo.nodes.some((n) => n.id === workerGraphId('get_md:file_id=7'))).toBe(true)
  })

  it('derives per-worker node states from task_key', () => {
    const events = [
      ev({
        seq: 1,
        node_id: 'get_md_worker',
        phase: 'end',
        task_key: 'get_md:file_id=7',
      }),
      ev({
        seq: 2,
        node_id: 'get_md_worker',
        phase: 'start',
        task_key: 'get_md:file_id=9',
      }),
    ]
    const topo = buildDisplayTopology(events, 'kb_full')
    const states = deriveNodeStates(events, true, topo.nodes)
    expect(states[workerGraphId('get_md:file_id=7')]).toBe('done')
    expect(states[workerGraphId('get_md:file_id=9')]).toBe('active')
  })

  it('lights outgoing edges from the active worker node', () => {
    const events = [
      ev({ seq: 1, node_id: 'assess', phase: 'end' }),
      ev({
        seq: 2,
        node_id: 'get_md_worker',
        phase: 'start',
        task_key: 'get_md:file_id=7',
      }),
      ev({
        seq: 3,
        node_id: 'get_md_worker',
        phase: 'start',
        task_key: 'get_md:file_id=9',
      }),
    ]
    const topo = buildDisplayTopology(events, 'kb_full')
    const lit = activeEdgeKeys(events, true, topo.edges, topo.nodes)
    expect(lit.has(`${workerGraphId('get_md:file_id=9')}->verify_evidence`)).toBe(true)
  })

  it('extracts module hints from summary_json', () => {
    const hints = extractModuleHints({
      module_hints: [
        {
          intent: 'research',
          reason: '外网显式触发词',
          next_action: '调用 research 子流程',
          module_ids: ['research'],
        },
      ],
    })
    expect(hints).toHaveLength(1)
    expect(hints[0].intent).toBe('research')
  })
})
