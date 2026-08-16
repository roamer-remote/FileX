/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App, ConfigProvider } from 'antd'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { AgentRunDetailResponse, AgentRunEvent } from '@/api/agentRuns'
import AgentRunDetailPage from './AgentRunDetail'

const getAgentRun = vi.fn()

vi.mock('@/api/agentRuns', () => ({
  getAgentRun: (...args: unknown[]) => getAgentRun(...args),
  getAgentRunEventsDelta: vi.fn(),
}))

vi.mock('@/lib/fetchEventSource', () => ({
  fetchEventSource: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('@/utils', () => ({
  formatDate: (v: string) => v,
}))

vi.mock('@/components/AgentRunSessionTree', () => ({
  default: () => <div data-testid="session-tree" />,
}))

vi.mock('@/components/AgentRunBranchDetail', () => ({
  default: ({ branch }: { branch: { kind: string } | null }) =>
    branch ? <div data-testid={`branch-detail-${branch.kind}`} /> : null,
}))

vi.mock('@/components/AgentRunModuleHintPanel', () => ({
  default: () => <div data-testid="module-hint" />,
}))

vi.mock('@/components/AgentRunTimeline', () => ({
  default: () => <div data-testid="timeline" />,
}))

vi.mock('@/components/AgentRunSearchTraceDrawer', () => ({
  default: () => null,
}))

function ev(partial: Partial<AgentRunEvent> & Pick<AgentRunEvent, 'seq' | 'node_id' | 'phase'>): AgentRunEvent {
  return {
    attempt: 1,
    ts: '2026-07-03T10:00:00+08:00',
    layer: partial.layer ?? 'kb',
    label: partial.label ?? partial.node_id,
    ...partial,
  }
}

function searchPair(seqStart: number, taskKey: string, hitCount: number): AgentRunEvent[] {
  return [
    ev({
      seq: seqStart,
      layer: 'tool',
      node_id: 'kb_search',
      label: '资料库检索',
      phase: 'start',
      task_key: taskKey,
    }),
    ev({
      seq: seqStart + 1,
      layer: 'tool',
      node_id: 'kb_search',
      label: '资料库检索',
      phase: 'end',
      task_key: taskKey,
      meta_json: { hit_count: hitCount },
    }),
  ]
}

function runDetail(events: AgentRunEvent[], overrides: Partial<AgentRunDetailResponse> = {}): AgentRunDetailResponse {
  return {
    id: 'run-test',
    question_preview: '测试问题',
    status: 'completed',
    started_at: '2026-07-03T10:00:00+08:00',
    events,
    ...overrides,
  }
}

async function renderDetail() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root: Root = createRoot(container)
  await act(async () => {
    root.render(
      <ConfigProvider>
        <App>
          <MemoryRouter initialEntries={['/agent/runs/run-test']}>
            <Routes>
              <Route path="/agent/runs/:runId" element={<AgentRunDetailPage />} />
            </Routes>
          </MemoryRouter>
        </App>
      </ConfigProvider>,
    )
  })
  await act(async () => {
    await Promise.resolve()
  })
  return { container, root }
}

describe('AgentRunDetailPage integration', () => {
  beforeEach(() => {
    getAgentRun.mockReset()
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('search-only shows session tree and search branch without FlowGraph or ModuleHint (SC-110-01)', async () => {
    getAgentRun.mockResolvedValue({
      data: runDetail([
        ...searchPair(1, 'search:aaa111222333', 1),
        ...searchPair(3, 'search:bbb444555666', 2),
      ]),
    })
    await renderDetail()
    expect(document.body.querySelector('[data-testid="session-tree"]')).toBeTruthy()
    expect(document.body.querySelector('[data-testid="branch-detail-search"]')).toBeTruthy()
    expect(document.body.querySelector('[data-testid="branch-detail-langgraph"]')).toBeFalsy()
    expect(document.body.querySelector('[data-testid="module-hint"]')).toBeFalsy()
  })

  it('mixed session hides ModuleHint when search branches exist (P-110-05)', async () => {
    getAgentRun.mockResolvedValue({
      data: runDetail([
        ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'end' }),
        ev({ seq: 2, layer: 'router', node_id: 'emit_hint', phase: 'end' }),
        ...searchPair(3, 'search:ccc777888999', 1),
      ]),
    })
    await renderDetail()
    expect(document.body.querySelector('[data-testid="session-tree"]')).toBeTruthy()
    expect(document.body.querySelector('[data-testid="module-hint"]')).toBeFalsy()
  })

  it('router-only legacy shows ModuleHint and langgraph branch without session tree chrome (SC-110-06)', async () => {
    getAgentRun.mockResolvedValue({
      data: runDetail([
        ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'end' }),
        ev({ seq: 2, layer: 'router', node_id: 'emit_hint', phase: 'end' }),
      ]),
    })
    await renderDetail()
    expect(document.body.querySelector('[data-testid="session-tree"]')).toBeFalsy()
    expect(document.body.querySelector('[data-testid="branch-detail-langgraph"]')).toBeTruthy()
    expect(document.body.querySelector('[data-testid="module-hint"]')).toBeTruthy()
  })

  it('legacy kb_full hides session tree and shows langgraph branch (SC-110-06 layout)', async () => {
    getAgentRun.mockResolvedValue({
      data: runDetail([
        ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'end', duration_ms: 1230 }),
        ev({ seq: 2, layer: 'router', node_id: 'preflight_global', phase: 'end', duration_ms: 750 }),
        ev({ seq: 3, layer: 'router', node_id: 'kb_search_branch', phase: 'end', duration_ms: 480 }),
        ev({ seq: 4, node_id: 'classify_query', phase: 'end', duration_ms: 890 }),
        ev({ seq: 5, node_id: 'initial_search', phase: 'end', duration_ms: 1640 }),
        ev({ seq: 6, node_id: 'assess', phase: 'end', duration_ms: 920 }),
        ev({ seq: 7, node_id: 'get_md_worker', phase: 'start', task_key: 'get_md:file_id=327' }),
        ev({ seq: 8, node_id: 'get_md_worker', phase: 'start', task_key: 'get_md:file_id=418' }),
      ]),
    })
    await renderDetail()
    expect(document.body.querySelector('[data-testid="session-tree"]')).toBeFalsy()
    expect(document.body.querySelector('[data-testid="branch-detail-langgraph"]')).toBeTruthy()
    expect(document.body.querySelector('[data-testid="module-hint"]')).toBeFalsy()
    expect(document.body.textContent).toContain('agentRuns.flowTitle')
  })

  it('search-only uses search branch section title (Suggestion 131000)', async () => {
    getAgentRun.mockResolvedValue({
      data: runDetail([
        ...searchPair(1, 'search:aaa111222333', 1),
        ...searchPair(3, 'search:bbb444555666', 2),
      ]),
    })
    await renderDetail()
    expect(document.body.textContent).toContain('agentRuns.searchBranchesTitle')
    expect(document.body.textContent).not.toContain('agentRuns.flowTitle')
  })
})
