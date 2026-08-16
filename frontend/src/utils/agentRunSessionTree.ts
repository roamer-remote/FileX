import type { AgentRunEvent } from '@/api/agentRuns'

export type SessionBranchKind = 'langgraph' | 'search'

export type SessionBranchStatus = 'idle' | 'running' | 'done' | 'error'

export type SessionViewMode =
  | 'session_search_only'
  | 'session_mixed'
  | 'session_single_kb'
  | 'session_router_only'

export type SessionBranch = {
  /** Stable across incremental event merges when possible */
  id: string
  kind: SessionBranchKind
  events: AgentRunEvent[]
  taskKey?: string
  langGraphIndex?: number
  firstSeq: number
  status: SessionBranchStatus
}

function isKbSearchToolEvent(ev: AgentRunEvent): boolean {
  return ev.layer === 'tool' && ev.node_id === 'kb_search'
}

function isLangGraphLayerEvent(ev: AgentRunEvent): boolean {
  return ev.layer === 'router' || ev.layer === 'kb'
}

function isClassifyInvokeStart(ev: AgentRunEvent): boolean {
  return ev.node_id === 'classify' && ev.phase === 'start'
}

export function formatSearchTaskKeyShort(taskKey: string): string {
  const match = taskKey.match(/^search:([0-9a-f]{12})$/i)
  if (match) return match[1].slice(-8)
  const hex = taskKey.replace(/^search:/i, '')
  if (/^[0-9a-f]+$/i.test(hex) && hex.length >= 8) return hex.slice(-8)
  return taskKey.slice(-8)
}

function deriveBranchStatus(events: AgentRunEvent[], running: boolean): SessionBranchStatus {
  if (events.some((ev) => ev.phase === 'error')) return 'error'
  const hasOpenStart = events.some((ev) => {
    if (ev.phase !== 'start') return false
    const closed = events.some(
      (other) =>
        other.seq > ev.seq &&
        other.node_id === ev.node_id &&
        other.task_key === ev.task_key &&
        other.span_id === ev.span_id &&
        (other.phase === 'end' || other.phase === 'error'),
    )
    return !closed
  })
  if (hasOpenStart && running) return 'running'
  if (events.length === 0) return 'idle'
  const last = events[events.length - 1]
  if (last.phase === 'start' && running) return 'running'
  return 'done'
}

function splitLangGraphSegments(events: AgentRunEvent[]): AgentRunEvent[][] {
  const lgEvents = events.filter(isLangGraphLayerEvent)
  if (lgEvents.length === 0) return []

  const invokeStarts = lgEvents.filter(isClassifyInvokeStart).map((ev) => ev.seq)
  if (invokeStarts.length === 0) {
    return [lgEvents]
  }

  const segments: AgentRunEvent[][] = []
  for (let i = 0; i < invokeStarts.length; i += 1) {
    const startSeq = invokeStarts[i]
    const endSeq = i + 1 < invokeStarts.length ? invokeStarts[i + 1] : Infinity
    const slice = lgEvents.filter((ev) => ev.seq >= startSeq && ev.seq < endSeq)
    if (slice.length > 0) segments.push(slice)
  }

  const firstStart = invokeStarts[0]
  const beforeFirst = lgEvents.filter((ev) => ev.seq < firstStart)
  if (beforeFirst.length > 0) {
    segments.unshift(beforeFirst)
  }

  return segments
}

function attachParentSeqEvents(
  segments: AgentRunEvent[][],
  allEvents: AgentRunEvent[],
): AgentRunEvent[][] {
  const seqToSegment = new Map<number, number>()
  for (let i = 0; i < segments.length; i += 1) {
    for (const ev of segments[i]) {
      seqToSegment.set(ev.seq, i)
    }
  }

  const orphanLangGraph: AgentRunEvent[] = []
  for (const ev of allEvents) {
    if (isKbSearchToolEvent(ev)) continue
    if (seqToSegment.has(ev.seq)) continue
    if (ev.parent_seq != null && seqToSegment.has(ev.parent_seq)) {
      const segIdx = seqToSegment.get(ev.parent_seq)!
      segments[segIdx] = [...segments[segIdx], ev].sort((a, b) => a.seq - b.seq)
      seqToSegment.set(ev.seq, segIdx)
    } else if (isLangGraphLayerEvent(ev)) {
      orphanLangGraph.push(ev)
    }
  }

  if (orphanLangGraph.length > 0 && segments.length > 0) {
    segments[0] = [...orphanLangGraph, ...segments[0]].sort((a, b) => a.seq - b.seq)
    for (const ev of orphanLangGraph) seqToSegment.set(ev.seq, 0)
  } else if (orphanLangGraph.length > 0) {
    segments.push(orphanLangGraph)
  }

  return segments
}

function buildSearchBranches(events: AgentRunEvent[], running: boolean): SessionBranch[] {
  const byKey = new Map<string, AgentRunEvent[]>()
  for (const ev of events) {
    if (!isKbSearchToolEvent(ev)) continue
    const key = ev.task_key?.trim()
    if (!key) continue
    const list = byKey.get(key) ?? []
    list.push(ev)
    byKey.set(key, list)
  }

  const branches: SessionBranch[] = []
  for (const [taskKey, branchEvents] of byKey.entries()) {
    const sorted = [...branchEvents].sort((a, b) => a.seq - b.seq)
    branches.push({
      id: taskKey,
      kind: 'search',
      events: sorted,
      taskKey,
      firstSeq: sorted[0].seq,
      status: deriveBranchStatus(sorted, running),
    })
  }
  return branches
}

function buildLangGraphBranches(events: AgentRunEvent[], running: boolean): SessionBranch[] {
  let segments = splitLangGraphSegments(events)
  segments = attachParentSeqEvents(segments, events)

  return segments.map((segmentEvents, index) => {
    const sorted = [...segmentEvents].sort((a, b) => a.seq - b.seq)
    const firstSeq = sorted[0]?.seq ?? 0
    return {
      id: `langgraph:${index + 1}:${firstSeq}`,
      kind: 'langgraph' as const,
      events: sorted,
      langGraphIndex: index + 1,
      firstSeq,
      status: deriveBranchStatus(sorted, running),
    }
  })
}

export function buildSessionBranches(
  events: AgentRunEvent[],
  running = false,
): SessionBranch[] {
  const sorted = [...events].sort((a, b) => a.seq - b.seq)
  const searchBranches = buildSearchBranches(sorted, running)
  const langGraphBranches = buildLangGraphBranches(sorted, running)
  return [...searchBranches, ...langGraphBranches].sort((a, b) => a.firstSeq - b.firstSeq)
}

export function langGraphBranches(branches: SessionBranch[]): SessionBranch[] {
  return branches.filter((b) => b.kind === 'langgraph')
}

export function searchBranches(branches: SessionBranch[]): SessionBranch[] {
  return branches.filter((b) => b.kind === 'search')
}

export function branchHasKbLayer(branch: SessionBranch): boolean {
  return branch.events.some((ev) => ev.layer === 'kb')
}

export function resolveSessionViewMode(branches: SessionBranch[]): SessionViewMode {
  const lg = langGraphBranches(branches)
  const search = searchBranches(branches)

  if (search.length >= 1 && lg.length === 0) return 'session_search_only'
  if (search.length >= 1 && lg.length >= 1) return 'session_mixed'
  if (lg.length >= 2 && search.length === 0) return 'session_mixed'
  if (lg.length === 1 && search.length === 0) {
    return branchHasKbLayer(lg[0]) ? 'session_single_kb' : 'session_router_only'
  }
  return 'session_router_only'
}

export function shouldShowSessionTreeChrome(
  viewMode: SessionViewMode,
  branchCount: number,
): boolean {
  if (branchCount <= 1) return false
  if (viewMode === 'session_single_kb' || viewMode === 'session_router_only') {
    return false
  }
  return true
}

export function searchBranchHitCount(branch: SessionBranch): number | undefined {
  if (branch.kind !== 'search') return undefined
  for (let i = branch.events.length - 1; i >= 0; i -= 1) {
    const ev = branch.events[i]
    if (ev.phase !== 'end') continue
    const raw = ev.meta_json?.hit_count
    if (typeof raw === 'number') return raw
  }
  return undefined
}

export function branchDurationMs(branch: SessionBranch): number | undefined {
  let total = 0
  let found = false
  for (const ev of branch.events) {
    if (ev.phase === 'end' && ev.duration_ms != null) {
      total += ev.duration_ms
      found = true
    }
  }
  return found ? total : undefined
}

export function compactEventTime(ts?: string): string | undefined {
  if (!ts) return undefined
  const match = ts.match(/T(\d{2}:\d{2}:\d{2})/)
  if (match) return match[1]
  return ts
}

/** 默认选中：保留用户选择；否则 running 分支；否则最新分支 */
export function pickDefaultBranchId(
  branches: SessionBranch[],
  preferredId: string | null = null,
): string | null {
  if (branches.length === 0) return null
  if (preferredId && branches.some((b) => b.id === preferredId)) return preferredId
  const running = branches.find((b) => b.status === 'running')
  if (running) return running.id
  return branches[branches.length - 1]!.id
}

/** FR-110-001：LangGraph 分支副标题（classify label 或时间） */
export function langGraphBranchSubtitle(branch: SessionBranch): string | undefined {
  if (branch.kind !== 'langgraph') return undefined
  const classify = branch.events.find((ev) => ev.node_id === 'classify')
  if (classify) {
    if (classify.label && classify.label !== classify.node_id) return classify.label
    const time = compactEventTime(classify.ts)
    if (time) return time
  }
  const first = branch.events[0]
  if (!first) return undefined
  if (first.label && first.label !== first.node_id) return first.label
  return compactEventTime(first.ts)
}

function formatBranchDurationMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/** FR-110-001 / FR-110-004：分支标题（会话树与时间轴分组共用） */
export function branchTitle(
  branch: SessionBranch,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  if (branch.kind === 'search' && branch.taskKey) {
    const short = formatSearchTaskKeyShort(branch.taskKey)
    const hits = searchBranchHitCount(branch)
    if (hits != null) {
      return t('agentRuns.sessionTree.searchBranchWithHits', { short, count: hits })
    }
    return t('agentRuns.sessionTree.searchBranch', { short })
  }
  const detail = langGraphBranchSubtitle(branch)
  if (detail) {
    return t('agentRuns.sessionTree.langGraphPathDetail', {
      n: branch.langGraphIndex ?? 1,
      detail,
    })
  }
  return t('agentRuns.sessionTree.langGraphPath', {
    n: branch.langGraphIndex ?? 1,
  })
}

export function branchSummary(
  branch: SessionBranch,
  _t: (key: string, opts?: Record<string, unknown>) => string,
): string | undefined {
  const duration = branchDurationMs(branch)
  if (duration == null) return undefined
  return formatBranchDurationMs(duration)
}

/** FR-110-005：search-only 时分支区标题与 LangGraph 流程区分 */
export function branchDetailSectionTitle(
  viewMode: SessionViewMode,
  t: (key: string) => string,
): string {
  if (viewMode === 'session_search_only') return t('agentRuns.searchBranchesTitle')
  return t('agentRuns.flowTitle')
}
