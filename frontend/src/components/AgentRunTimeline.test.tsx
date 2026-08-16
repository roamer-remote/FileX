/**
 * @vitest-environment jsdom
 */

import { type ComponentProps } from 'react'
import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AgentRunEvent } from '@/api/agentRuns'
import AgentRunTimeline from './AgentRunTimeline'
import type { SessionBranch } from '@/utils/agentRunSessionTree'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (key === 'agentRuns.sessionTree.searchBranchWithHits') {
        return `Search ${opts?.short} hits ${opts?.count}`
      }
      if (key === 'agentRuns.sessionTree.langGraphPath') return `LangGraph #${opts?.n}`
      return key
    },
  }),
}))

vi.mock('@/utils', () => ({
  formatDate: (v: string) => v,
}))

function ev(partial: Partial<AgentRunEvent> & Pick<AgentRunEvent, 'seq' | 'node_id' | 'phase'>): AgentRunEvent {
  return {
    attempt: 1,
    ts: '2026-07-03T10:00:00+08:00',
    layer: partial.layer ?? 'tool',
    label: partial.label ?? partial.node_id,
    ...partial,
  }
}

const branches: SessionBranch[] = [
  {
    id: 'search:aaa111222333',
    kind: 'search',
    taskKey: 'search:aaa111222333',
    firstSeq: 1,
    status: 'done',
    events: [
      ev({ seq: 1, node_id: 'kb_search', phase: 'start', task_key: 'search:aaa111222333' }),
      ev({ seq: 2, node_id: 'kb_search', phase: 'end', task_key: 'search:aaa111222333' }),
    ],
  },
  {
    id: 'search:bbb444555666',
    kind: 'search',
    taskKey: 'search:bbb444555666',
    firstSeq: 3,
    status: 'done',
    events: [
      ev({ seq: 3, node_id: 'kb_search', phase: 'start', task_key: 'search:bbb444555666' }),
      ev({ seq: 4, node_id: 'kb_search', phase: 'end', task_key: 'search:bbb444555666' }),
    ],
  },
]

const events = branches.flatMap((b) => b.events)

const mountedRoots: Root[] = []

async function renderTimeline(props: Partial<ComponentProps<typeof AgentRunTimeline>> = {}) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root: Root = createRoot(container)
  mountedRoots.push(root)
  await act(async () => {
    root.render(<AgentRunTimeline events={events} branches={branches} {...props} />)
  })
  return { container, root }
}

describe('AgentRunTimeline', () => {
  afterEach(async () => {
    await act(async () => {
      while (mountedRoots.length > 0) {
        mountedRoots.pop()?.unmount()
      }
    })
    document.body.innerHTML = ''
  })

  it('shows grouped collapse panels when multiple branches', async () => {
    await renderTimeline()
    expect(document.body.querySelector('.agent-run-timeline__groups')).toBeTruthy()
    expect(document.body.querySelectorAll('.ant-collapse-item')).toHaveLength(2)
  })

  it('switches to flat table when flat mode selected', async () => {
    await renderTimeline()
    const flatBtn = [...document.body.querySelectorAll('.ant-segmented-item')].find((el) =>
      el.textContent?.includes('agentRuns.timelineFlat'),
    )
    expect(flatBtn).toBeTruthy()
    await act(async () => {
      flatBtn?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(document.body.querySelector('.agent-run-timeline__groups')).toBeFalsy()
    expect(document.body.querySelector('.ant-table')).toBeTruthy()
  })

  it('defaults to grouped when branches grow from one to many', async () => {
    const singleBranch = [branches[0]]
    const singleEvents = singleBranch.flatMap((b) => b.events)
    const { root } = await renderTimeline({ events: singleEvents, branches: singleBranch })
    expect(document.body.querySelector('.agent-run-timeline__groups')).toBeFalsy()

    await act(async () => {
      root.render(<AgentRunTimeline events={events} branches={branches} />)
    })
    expect(document.body.querySelector('.agent-run-timeline__groups')).toBeTruthy()
  })

  it('expands newly appended branch panels while grouped (SSE incremental)', async () => {
    const singleBranch = [branches[0]]
    const singleEvents = singleBranch.flatMap((b) => b.events)
    const { root } = await renderTimeline({ events: singleEvents, branches: singleBranch })

    await act(async () => {
      root.render(<AgentRunTimeline events={events} branches={branches} />)
    })
    expect(document.body.querySelectorAll('.ant-collapse-item')).toHaveLength(2)
    expect(document.body.querySelectorAll('.ant-collapse-item-active')).toHaveLength(2)

    const thirdBranch: SessionBranch = {
      id: 'search:ccc777888999',
      kind: 'search',
      taskKey: 'search:ccc777888999',
      firstSeq: 5,
      status: 'done',
      events: [
        ev({ seq: 5, node_id: 'kb_search', phase: 'start', task_key: 'search:ccc777888999' }),
        ev({ seq: 6, node_id: 'kb_search', phase: 'end', task_key: 'search:ccc777888999' }),
      ],
    }
    const threeBranches = [...branches, thirdBranch]
    const threeEvents = threeBranches.flatMap((b) => b.events)

    await act(async () => {
      root.render(<AgentRunTimeline events={threeEvents} branches={threeBranches} />)
    })
    expect(document.body.querySelectorAll('.ant-collapse-item')).toHaveLength(3)
    expect(document.body.querySelectorAll('.ant-collapse-item-active')).toHaveLength(3)
  })
})
