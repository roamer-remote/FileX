import { describe, expect, it } from 'vitest'
import type { AgentRunEvent } from '@/api/agentRuns'
import {
  branchTitle,
  buildSessionBranches,
  formatSearchTaskKeyShort,
  langGraphBranchSubtitle,
  pickDefaultBranchId,
  resolveSessionViewMode,
  searchBranches,
  langGraphBranches,
  shouldShowSessionTreeChrome,
} from './agentRunSessionTree'

function ev(partial: Partial<AgentRunEvent> & Pick<AgentRunEvent, 'seq' | 'node_id' | 'phase'>): AgentRunEvent {
  return {
    attempt: 1,
    ts: '2026-07-03T15:24:31+08:00',
    layer: partial.layer ?? 'kb',
    label: partial.label ?? partial.node_id,
    ...partial,
  }
}

/** Same sequence as AgentRunFlowGraph.test.tsx legacy kb_full path */
const LEGACY_KB_FULL_EVENTS: AgentRunEvent[] = [
  ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'end', duration_ms: 1230 }),
  ev({ seq: 2, layer: 'router', node_id: 'preflight_global', phase: 'end', duration_ms: 750 }),
  ev({ seq: 3, layer: 'router', node_id: 'kb_search_branch', phase: 'end', duration_ms: 480 }),
  ev({ seq: 4, node_id: 'classify_query', phase: 'end', duration_ms: 890 }),
  ev({ seq: 5, node_id: 'initial_search', phase: 'end', duration_ms: 1640 }),
  ev({ seq: 6, node_id: 'assess', phase: 'end', duration_ms: 920 }),
  ev({ seq: 7, node_id: 'get_md_worker', phase: 'start', task_key: 'get_md:file_id=327' }),
  ev({ seq: 8, node_id: 'get_md_worker', phase: 'start', task_key: 'get_md:file_id=418' }),
]

function searchPair(seqStart: number, taskKey: string, hitCount: number): AgentRunEvent[] {
  const span = `span-${seqStart}`
  return [
    ev({
      seq: seqStart,
      layer: 'tool',
      node_id: 'kb_search',
      label: '资料库检索',
      phase: 'start',
      task_key: taskKey,
      span_id: span,
    }),
    ev({
      seq: seqStart + 1,
      layer: 'tool',
      node_id: 'kb_search',
      label: '资料库检索',
      phase: 'end',
      task_key: taskKey,
      span_id: span,
      duration_ms: 120,
      meta_json: { hit_count: hitCount },
    }),
  ]
}

describe('formatSearchTaskKeyShort', () => {
  it('uses last 8 hex digits of search fingerprint', () => {
    expect(formatSearchTaskKeyShort('search:a434a7670c7c')).toBe('a7670c7c')
    expect(formatSearchTaskKeyShort('search:abcdef012345')).toBe('ef012345')
  })
})

describe('buildSessionBranches', () => {
  it('legacy single invoke kb_full → one langgraph branch with parallel get_md workers', () => {
    const branches = buildSessionBranches(LEGACY_KB_FULL_EVENTS)
    expect(langGraphBranches(branches)).toHaveLength(1)
    expect(searchBranches(branches)).toHaveLength(0)
    expect(resolveSessionViewMode(branches)).toBe('session_single_kb')
    expect(shouldShowSessionTreeChrome(resolveSessionViewMode(branches), branches.length)).toBe(false)
    const seqs = langGraphBranches(branches)[0].events.map((e) => e.seq)
    expect(seqs).toContain(7)
    expect(seqs).toContain(8)
    expect(langGraphBranchSubtitle(langGraphBranches(branches)[0])).toBeTruthy()
  })

  it('search-only with two parallel task_keys', () => {
    const events = [
      ...searchPair(1, 'search:aaa111222333', 1),
      ...searchPair(3, 'search:bbb444555666', 3),
    ]
    const branches = buildSessionBranches(events)
    expect(searchBranches(branches)).toHaveLength(2)
    expect(langGraphBranches(branches)).toHaveLength(0)
    expect(resolveSessionViewMode(branches)).toBe('session_search_only')
    expect(branches.map((b) => b.firstSeq)).toEqual([1, 3])
  })

  it('mixed: langgraph + two searches + second langgraph invoke', () => {
    const events: AgentRunEvent[] = [
      ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'start' }),
      ev({ seq: 2, layer: 'router', node_id: 'classify', phase: 'end' }),
      ev({ seq: 3, layer: 'kb', node_id: 'initial_search', phase: 'end' }),
      ...searchPair(4, 'search:111111111111', 2),
      ...searchPair(6, 'search:222222222222', 1),
      ev({ seq: 8, layer: 'router', node_id: 'classify', phase: 'start' }),
      ev({ seq: 9, layer: 'router', node_id: 'emit_hint', phase: 'end' }),
    ]
    const branches = buildSessionBranches(events)
    expect(langGraphBranches(branches)).toHaveLength(2)
    expect(searchBranches(branches)).toHaveLength(2)
    expect(resolveSessionViewMode(branches)).toBe('session_mixed')
    expect(branches.map((b) => b.firstSeq)).toEqual([1, 4, 6, 8])
  })

  it('router_only single langgraph without kb layer', () => {
    const events: AgentRunEvent[] = [
      ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'start' }),
      ev({ seq: 2, layer: 'router', node_id: 'classify', phase: 'end' }),
      ev({ seq: 3, layer: 'router', node_id: 'emit_hint', phase: 'end' }),
    ]
    const branches = buildSessionBranches(events)
    expect(resolveSessionViewMode(branches)).toBe('session_router_only')
    expect(langGraphBranches(branches)).toHaveLength(1)
  })

  it('multiple langgraph segments without search → session_mixed', () => {
    const events: AgentRunEvent[] = [
      ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'start' }),
      ev({ seq: 2, layer: 'kb', node_id: 'initial_search', phase: 'end' }),
      ev({ seq: 3, layer: 'router', node_id: 'classify', phase: 'start' }),
      ev({ seq: 4, layer: 'kb', node_id: 'synthesize', phase: 'end' }),
    ]
    const branches = buildSessionBranches(events)
    expect(langGraphBranches(branches)).toHaveLength(2)
    expect(resolveSessionViewMode(branches)).toBe('session_mixed')
  })

  it('parent_seq child stays in langgraph branch', () => {
    const events: AgentRunEvent[] = [
      ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'start', client_event_id: 'c1' }),
      ev({ seq: 2, node_id: 'get_md_worker', phase: 'start', task_key: 'get_md:file_id=1' }),
      ev({
        seq: 3,
        node_id: 'get_md_worker',
        phase: 'end',
        task_key: 'get_md:file_id=1',
        parent_seq: 2,
      }),
    ]
    const branches = buildSessionBranches(events)
    expect(langGraphBranches(branches)).toHaveLength(1)
    expect(langGraphBranches(branches)[0].events.map((e) => e.seq)).toEqual([1, 2, 3])
  })

  it('empty events → session_router_only', () => {
    const branches = buildSessionBranches([])
    expect(branches).toHaveLength(0)
    expect(resolveSessionViewMode(branches)).toBe('session_router_only')
  })

  it('marks branch running when open start and running=true', () => {
    const events = searchPair(1, 'search:aaa111222333', 1).slice(0, 1)
    const branches = buildSessionBranches(events, true)
    expect(branches[0].status).toBe('running')
    const done = buildSessionBranches(searchPair(1, 'search:aaa111222333', 1), true)
    expect(done[0].status).toBe('done')
  })

  it('marks langgraph branch running on open worker start', () => {
    const events: AgentRunEvent[] = [
      ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'end' }),
      ev({ seq: 2, node_id: 'get_md_worker', phase: 'start', task_key: 'get_md:file_id=1' }),
    ]
    expect(buildSessionBranches(events, true)[0].status).toBe('running')
    expect(buildSessionBranches(events, false)[0].status).toBe('done')
  })

  it('stable branch ids when appending search events', () => {
    const keyA = 'search:aaa111222333'
    const keyB = 'search:bbb444555666'
    const initial = searchPair(1, keyA, 1)
    const first = buildSessionBranches(initial)
    const merged = buildSessionBranches([...initial, ...searchPair(3, keyB, 2)])
    expect(first[0].id).toBe(keyA)
    expect(merged[0].id).toBe(keyA)
    expect(merged[1].id).toBe(keyB)
  })

  it('stable langgraph branch ids when second invoke segment appends', () => {
    const segment1: AgentRunEvent[] = [
      ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'start' }),
      ev({ seq: 2, layer: 'kb', node_id: 'initial_search', phase: 'end' }),
    ]
    const first = buildSessionBranches(segment1)
    const merged = buildSessionBranches([
      ...segment1,
      ev({ seq: 3, layer: 'router', node_id: 'classify', phase: 'start' }),
      ev({ seq: 4, layer: 'router', node_id: 'emit_hint', phase: 'end' }),
    ])
    expect(first[0].id).toBe('langgraph:1:1')
    expect(merged[0].id).toBe('langgraph:1:1')
    expect(merged[1].id).toBe('langgraph:2:3')
  })
})

describe('pickDefaultBranchId', () => {
  it('keeps preferred id when branch still exists after merge (SC-110-07)', () => {
    const keyA = 'search:aaa111222333'
    const keyB = 'search:bbb444555666'
    const initial = searchPair(1, keyA, 1)
    const first = buildSessionBranches(initial)
    const preferred = first[0].id
    const merged = buildSessionBranches([...initial, ...searchPair(3, keyB, 2)])
    expect(pickDefaultBranchId(merged, preferred)).toBe(preferred)
    expect(pickDefaultBranchId(merged, null)).toBe(keyB)
  })

  it('prefers running branch over last branch', () => {
    const events: AgentRunEvent[] = [
      ev({ seq: 1, layer: 'tool', node_id: 'kb_search', phase: 'start', task_key: 'search:done111111111' }),
      ev({ seq: 2, layer: 'tool', node_id: 'kb_search', phase: 'end', task_key: 'search:done111111111' }),
      ev({ seq: 3, layer: 'tool', node_id: 'kb_search', phase: 'start', task_key: 'search:run2222222222' }),
    ]
    const branches = buildSessionBranches(events, true)
    expect(pickDefaultBranchId(branches, null)).toBe('search:run2222222222')
  })
})

describe('branchTitle', () => {
  const mockT = (key: string, opts?: Record<string, unknown>) => {
    if (key === 'agentRuns.sessionTree.langGraphPathDetail') {
      return `LangGraph #${opts?.n} · ${opts?.detail}`
    }
    if (key === 'agentRuns.sessionTree.searchBranchWithHits') {
      return `Search ${opts?.short} hits ${opts?.count}`
    }
    return key
  }

  it('formats langgraph branch with subtitle', () => {
    const branches = buildSessionBranches([
      ev({ seq: 1, layer: 'router', node_id: 'classify', phase: 'end', label: '理解意图' }),
    ])
    expect(branchTitle(langGraphBranches(branches)[0], mockT)).toBe('LangGraph #1 · 理解意图')
  })

  it('formats search branch with hits', () => {
    const branches = buildSessionBranches(searchPair(1, 'search:aaa111222333', 5))
    expect(branchTitle(branches[0], mockT)).toBe('Search 11222333 hits 5')
  })
})
