/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AgentRunEvent } from '@/api/agentRuns'
import { buildSessionBranches, langGraphBranches } from '@/utils/agentRunSessionTree'
import AgentRunFlowGraph from './AgentRunFlowGraph'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const labels: Record<string, string> = {
        'agentRuns.flowGraph.labels.classify': 'Understand intent',
        'agentRuns.flowGraph.labels.preflightGlobal': 'Check access',
        'agentRuns.flowGraph.labels.kbSearchBranch': 'Enter library',
        'agentRuns.flowGraph.labels.preflight': 'Prepare search',
        'agentRuns.flowGraph.labels.classifyQuery': 'Analyze question',
        'agentRuns.flowGraph.labels.initialSearch': 'Search',
        'agentRuns.flowGraph.labels.assess': 'Assess evidence',
        'agentRuns.flowGraph.labels.getMdWorker': 'Read document',
        'agentRuns.flowGraph.labels.wikiExpand': 'Expand Wiki',
        'agentRuns.flowGraph.labels.verifyEvidence': 'Verify',
        'agentRuns.flowGraph.labels.synthesize': 'Synthesize',
      }
      return labels[key] ?? key
    },
  }),
}))

function ev(partial: Partial<AgentRunEvent> & Pick<AgentRunEvent, 'seq' | 'node_id' | 'phase'>): AgentRunEvent {
  return {
    attempt: 1,
    ts: '2026-07-03T15:24:31+08:00',
    layer: partial.layer ?? 'kb',
    label: partial.label ?? partial.node_id,
    ...partial,
  }
}

async function renderGraph(events: AgentRunEvent[], running = true) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root: Root = createRoot(container)

  await act(async () => {
    root.render(<AgentRunFlowGraph events={events} running={running} />)
  })

  return { container, root }
}

describe('AgentRunFlowGraph', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('renders the approved trace-canvas design with lanes, svg flow edges, and parallel get_md workers', async () => {
    await renderGraph([
      ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'end', duration_ms: 1230 }),
      ev({ seq: 2, layer: 'router', node_id: 'preflight_global', phase: 'end', duration_ms: 750 }),
      ev({ seq: 3, layer: 'router', node_id: 'kb_search_branch', phase: 'end', duration_ms: 480 }),
      ev({ seq: 4, node_id: 'classify_query', phase: 'end', duration_ms: 890 }),
      ev({ seq: 5, node_id: 'initial_search', phase: 'end', duration_ms: 1640 }),
      ev({ seq: 6, node_id: 'assess', phase: 'end', duration_ms: 920 }),
      ev({ seq: 7, node_id: 'get_md_worker', phase: 'start', task_key: 'get_md:file_id=327' }),
      ev({ seq: 8, node_id: 'get_md_worker', phase: 'start', task_key: 'get_md:file_id=418' }),
    ])

    expect(document.body.querySelector('.agent-run-flow__trace-canvas')).toBeTruthy()
    expect(document.body.querySelector('.agent-run-flow__svg')).toBeTruthy()
    expect(document.body.querySelector('[data-lane="L1"]')?.textContent).toBe('L1')
    expect(document.body.querySelector('[data-lane="L2"]')?.textContent).toBe('L2')
    expect(document.body.querySelectorAll('.agent-run-flow__node-card')).toHaveLength(12)
    expect(document.body.textContent).toContain('get_md:file_id=327')
    expect(document.body.textContent).toContain('get_md:file_id=418')
    expect(document.body.textContent).toContain('Search')
    expect(document.body.textContent).toContain('Read document')
    expect(document.body.textContent).toContain('Verify')
    expect(document.body.textContent).toContain('Synthesize')
    expect(document.body.textContent).toContain('Expand Wiki')
    expect(document.body.textContent).toContain('Understand intent')
    expect(document.body.textContent).not.toContain('理解意图')
    expect(document.body.textContent).not.toContain('生成回答')
  })

  it('shows a single get_md task key only on the worker node', async () => {
    await renderGraph([
      ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'end', duration_ms: 1230 }),
      ev({ seq: 2, layer: 'router', node_id: 'preflight_global', phase: 'end', duration_ms: 750 }),
      ev({ seq: 3, layer: 'router', node_id: 'kb_search_branch', phase: 'end', duration_ms: 480 }),
      ev({ seq: 4, node_id: 'classify_query', phase: 'end', duration_ms: 890 }),
      ev({ seq: 5, node_id: 'initial_search', phase: 'end', duration_ms: 1640 }),
      ev({ seq: 6, node_id: 'assess', phase: 'end', duration_ms: 920 }),
      ev({ seq: 7, node_id: 'get_md_worker', phase: 'start', task_key: 'get_md:file_id=327' }),
    ])

    const badges = [...document.body.querySelectorAll('.agent-run-flow__task-key')]
    expect(badges).toHaveLength(1)
    expect(badges[0].textContent).toBe('get_md:file_id=327')
    expect(badges[0].closest('.agent-run-flow__node-card')?.textContent).toContain('Read document')
  })

  it('scoped branch events match full-run topology (SC-110-06)', async () => {
    const legacyEvents: AgentRunEvent[] = [
      ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'end', duration_ms: 1230 }),
      ev({ seq: 2, layer: 'router', node_id: 'preflight_global', phase: 'end', duration_ms: 750 }),
      ev({ seq: 3, layer: 'router', node_id: 'kb_search_branch', phase: 'end', duration_ms: 480 }),
      ev({ seq: 4, node_id: 'classify_query', phase: 'end', duration_ms: 890 }),
      ev({ seq: 5, node_id: 'initial_search', phase: 'end', duration_ms: 1640 }),
      ev({ seq: 6, node_id: 'assess', phase: 'end', duration_ms: 920 }),
      ev({ seq: 7, node_id: 'get_md_worker', phase: 'start', task_key: 'get_md:file_id=327' }),
      ev({ seq: 8, node_id: 'get_md_worker', phase: 'start', task_key: 'get_md:file_id=418' }),
    ]
    const scopedEvents = langGraphBranches(buildSessionBranches(legacyEvents))[0]!.events
    expect(scopedEvents.map((e) => e.seq)).toEqual(legacyEvents.map((e) => e.seq))

    await renderGraph(legacyEvents, false)
    const fullCount = document.body.querySelectorAll('.agent-run-flow__node-card').length
    document.body.innerHTML = ''
    await renderGraph(scopedEvents, false)
    const scopedCount = document.body.querySelectorAll('.agent-run-flow__node-card').length
    expect(scopedCount).toBe(fullCount)
    expect(scopedCount).toBe(12)
  })
})
