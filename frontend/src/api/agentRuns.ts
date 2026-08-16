import api from '@/api/index'

export type AgentRunSummary = {
  id: string
  thread_id?: string | null
  question_preview: string
  intent?: string | null
  status: string
  started_at: string
  finished_at?: string | null
  duration_ms?: number | null
  summary_json?: Record<string, unknown> | null
  username?: string | null
}

export type AgentRunEvent = {
  seq: number
  client_event_id?: string | null
  parent_seq?: number | null
  task_key?: string | null
  span_id?: string | null
  attempt: number
  ts: string
  layer: string
  node_id: string
  label: string
  phase: string
  duration_ms?: number | null
  meta_json?: Record<string, unknown> | null
}

export type AgentRunListResponse = {
  total: number
  items: AgentRunSummary[]
}

export type AgentRunDetailResponse = AgentRunSummary & {
  events: AgentRunEvent[]
}

export type AgentRunEventsDeltaResponse = {
  events: AgentRunEvent[]
  run_status: string
  latest_seq: number
}

export type AgentRunDeleteResponse = {
  deleted: number
}

export function listAgentRuns(params?: {
  page?: number
  page_size?: number
  thread_id?: string
  status?: string
  user_id?: number
  all_users?: boolean
}) {
  return api.get<AgentRunListResponse>('/agent-runs', { params })
}

export function getAgentRun(runId: string) {
  return api.get<AgentRunDetailResponse>(`/agent-runs/${runId}`)
}

export function getAgentRunEventsDelta(runId: string, sinceSeq: number) {
  return api.get<AgentRunEventsDeltaResponse>(`/agent-runs/${runId}/events`, {
    params: { since_seq: sinceSeq },
  })
}

export function deleteAgentRuns(ids: string[]) {
  return api.post<AgentRunDeleteResponse>('/agent-runs/delete', { ids })
}
