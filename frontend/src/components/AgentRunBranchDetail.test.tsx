/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentRunBranchDetail from './AgentRunBranchDetail'
import type { SessionBranch } from '@/utils/agentRunSessionTree'

vi.mock('./AgentRunFlowGraph', () => ({
  default: ({ events }: { events: unknown[] }) => (
    <div data-testid="flow-graph">nodes:{events.length}</div>
  ),
}))

vi.mock('./AgentRunSearchBranchCard', () => ({
  default: () => <div data-testid="search-card">search</div>,
}))

describe('AgentRunBranchDetail', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('mounts search card for search branch', async () => {
    const branch: SessionBranch = {
      id: 'search:x',
      kind: 'search',
      taskKey: 'search:x',
      firstSeq: 1,
      status: 'done',
      events: [],
    }
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    await act(async () => {
      root.render(<AgentRunBranchDetail branch={branch} />)
    })
    expect(document.body.querySelector('[data-testid="search-card"]')).toBeTruthy()
    expect(document.body.querySelector('[data-testid="flow-graph"]')).toBeFalsy()
  })

  it('mounts flow graph for langgraph branch', async () => {
    const branch: SessionBranch = {
      id: 'lg:1',
      kind: 'langgraph',
      langGraphIndex: 1,
      firstSeq: 1,
      status: 'done',
      events: [{ seq: 1, layer: 'router', node_id: 'classify', phase: 'end', label: 'x', attempt: 1, ts: 't' }],
    }
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    await act(async () => {
      root.render(<AgentRunBranchDetail branch={branch} />)
    })
    expect(document.body.querySelector('[data-testid="flow-graph"]')).toBeTruthy()
  })
})
