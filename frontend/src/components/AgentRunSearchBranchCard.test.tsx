/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentRunSearchBranchCard from './AgentRunSearchBranchCard'
import type { SessionBranch } from '@/utils/agentRunSessionTree'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (key === 'agentRuns.searchTraceHitCount') return `${opts?.count} hits`
      if (key === 'agentRuns.searchBranchCard.heading') return `Search ${opts?.short}`
      return key
    },
  }),
}))

vi.mock('@/utils', () => ({
  formatDate: (v: string) => v,
}))

const branch: SessionBranch = {
  id: 'search:abc123456789',
  kind: 'search',
  taskKey: 'search:abc123456789',
  firstSeq: 1,
  status: 'done',
  events: [
    {
      seq: 1,
      layer: 'tool',
      node_id: 'kb_search',
      phase: 'start',
      label: '资料库检索',
      attempt: 1,
      ts: '2026-07-03T10:00:00+08:00',
      task_key: 'search:abc123456789',
    },
    {
      seq: 2,
      layer: 'tool',
      node_id: 'kb_search',
      phase: 'end',
      label: '资料库检索',
      attempt: 1,
      ts: '2026-07-03T10:00:01+08:00',
      duration_ms: 220,
      task_key: 'search:abc123456789',
      meta_json: { hit_count: 3 },
    },
  ],
}

describe('AgentRunSearchBranchCard', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('renders hit count and fingerprint', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root: Root = createRoot(container)
    await act(async () => {
      root.render(<AgentRunSearchBranchCard branch={branch} />)
    })
    expect(document.body.textContent).toContain('3 hits')
    expect(document.body.textContent).toContain('search:abc123456789')
  })

  it('calls onDrillSearchTrace when L3 drill is available', async () => {
    const onDrill = vi.fn()
    const branchWithTrace: SessionBranch = {
      ...branch,
      events: [
        branch.events[0],
        {
          ...branch.events[1],
          meta_json: {
            hit_count: 3,
            search_trace_summary: { hit_count: 3, vector: { merged_unique: 3 } },
          },
        },
      ],
    }
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root: Root = createRoot(container)
    await act(async () => {
      root.render(<AgentRunSearchBranchCard branch={branchWithTrace} onDrillSearchTrace={onDrill} />)
    })
    const drillBtn = [...document.body.querySelectorAll('button')].find((el) =>
      el.textContent?.includes('agentRuns.searchTraceDrill'),
    )
    expect(drillBtn).toBeTruthy()
    drillBtn?.click()
    expect(onDrill).toHaveBeenCalledWith(branchWithTrace.events[1])
  })
})
