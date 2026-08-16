/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import AgentRunSessionTree, { branchTitle } from './AgentRunSessionTree'
import type { SessionBranch } from '@/utils/agentRunSessionTree'
import { langGraphBranchSubtitle } from '@/utils/agentRunSessionTree'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (key === 'agentRuns.sessionTree.langGraphPath') return `LangGraph #${opts?.n}`
      if (key === 'agentRuns.sessionTree.langGraphPathDetail') {
        return `LangGraph #${opts?.n} · ${opts?.detail}`
      }
      if (key === 'agentRuns.sessionTree.searchBranch') return `Search ${opts?.short}`
      if (key === 'agentRuns.sessionTree.searchBranchWithHits') {
        return `Search ${opts?.short} hits ${opts?.count}`
      }
      if (key.startsWith('agentRuns.sessionTree.status.')) return key.split('.').pop()!
      return key
    },
  }),
}))

const branches: SessionBranch[] = [
  {
    id: 'langgraph:1:1',
    kind: 'langgraph',
    langGraphIndex: 1,
    firstSeq: 1,
    status: 'done',
    events: [
      {
        seq: 1,
        layer: 'router',
        node_id: 'classify',
        phase: 'end',
        label: '理解意图',
        attempt: 1,
        ts: '2026-07-03T15:24:31+08:00',
      },
    ],
  },
  {
    id: 'search:aaa111222333',
    kind: 'search',
    taskKey: 'search:aaa111222333',
    firstSeq: 2,
    status: 'running',
    events: [
      {
        seq: 2,
        layer: 'tool',
        node_id: 'kb_search',
        phase: 'start',
        label: 'search',
        attempt: 1,
        ts: 't',
        task_key: 'search:aaa111222333',
      },
      {
        seq: 3,
        layer: 'tool',
        node_id: 'kb_search',
        phase: 'end',
        label: 'search',
        attempt: 1,
        ts: 't',
        task_key: 'search:aaa111222333',
        meta_json: { hit_count: 5 },
      },
    ],
  },
]

const mockT = (key: string, opts?: Record<string, unknown>) => {
  if (key === 'agentRuns.sessionTree.langGraphPath') return `LangGraph #${opts?.n}`
  if (key === 'agentRuns.sessionTree.langGraphPathDetail') return `LangGraph #${opts?.n} · ${opts?.detail}`
  if (key === 'agentRuns.sessionTree.searchBranch') return `Search ${opts?.short}`
  if (key === 'agentRuns.sessionTree.searchBranchWithHits') return `Search ${opts?.short} hits ${opts?.count}`
  return key
}

async function renderTree(props: Partial<ComponentProps<typeof AgentRunSessionTree>> = {}) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root: Root = createRoot(container)
  const onSelectBranch = vi.fn()

  await act(async () => {
    root.render(
      <AgentRunSessionTree
        questionPreview="测试问句"
        branches={branches}
        selectedBranchId="langgraph:1:1"
        onSelectBranch={onSelectBranch}
        {...props}
      />,
    )
  })

  return { container, root, onSelectBranch }
}

describe('branchTitle helpers', () => {
  it('includes classify label in langgraph title', () => {
    expect(branchTitle(branches[0], mockT)).toBe('LangGraph #1 · 理解意图')
  })

  it('includes hit count in search title', () => {
    expect(branchTitle(branches[1], mockT)).toBe('Search 11222333 hits 5')
  })

  it('langGraphBranchSubtitle prefers classify label', () => {
    expect(langGraphBranchSubtitle(branches[0])).toBe('理解意图')
  })
})

describe('AgentRunSessionTree', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('renders root preview and branch tabs with kind detail', async () => {
    await renderTree()
    expect(document.body.textContent).toContain('测试问句')
    expect(document.body.textContent).toContain('理解意图')
    expect(document.body.textContent).toContain('Search')
    expect(document.body.querySelectorAll('[role="tab"]')).toHaveLength(2)
  })

  it('calls onSelectBranch when a branch is clicked', async () => {
    const { onSelectBranch } = await renderTree()
    const tabs = document.body.querySelectorAll('[role="tab"]')
    await act(async () => {
      ;(tabs[1] as HTMLButtonElement).click()
    })
    expect(onSelectBranch).toHaveBeenCalledWith('search:aaa111222333')
  })

  it('shows running status on active search branch', async () => {
    await renderTree({ selectedBranchId: 'search:aaa111222333' })
    expect(document.body.textContent).toContain('running')
  })

  it('selects branch on Enter key', async () => {
    const { onSelectBranch } = await renderTree()
    const tab = document.body.querySelectorAll('[role="tab"]')[1] as HTMLButtonElement
    await act(async () => {
      tab.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    })
    expect(onSelectBranch).toHaveBeenCalledWith('search:aaa111222333')
  })

  it('selects branch on Space key', async () => {
    const { onSelectBranch } = await renderTree()
    const tab = document.body.querySelectorAll('[role="tab"]')[1] as HTMLButtonElement
    await act(async () => {
      tab.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }))
    })
    expect(onSelectBranch).toHaveBeenCalledWith('search:aaa111222333')
  })
})
