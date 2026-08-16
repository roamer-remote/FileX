export const KB_EVAL_PANEL = 'eval'
export const KB_EVAL_PREFILL_QUERY_PARAM = 'prefill_query'
export const KB_EVAL_WORKSPACE_ID_PARAM = 'workspace_id'
export const KB_EVAL_TRIAL_CLIP_PARAM = 'trial_clip'

export type KbEvalLobbyLinkOptions = {
  prefillQuery?: string | null
  workspaceId?: number | null
  /** 无 prefill_query 时由大厅读剪贴板（chunk 试搜降级） */
  trialClip?: boolean
}

export function deriveChunkTrialSearchQuery(input: {
  boostKeywords?: string | null
  text?: string
  maxTextLen?: number
}): string {
  const boost = (input.boostKeywords ?? '').trim()
  if (boost) {
    const first = boost.split(/[,，]/).map((s) => s.trim()).find(Boolean)
    if (first) return first
  }
  const text = (input.text ?? '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  const maxLen = input.maxTextLen ?? 80
  return text.length <= maxLen ? text : text.slice(0, maxLen)
}

export function buildKbEvalLobbySearchParams(options: KbEvalLobbyLinkOptions): URLSearchParams {
  const params = new URLSearchParams()
  params.set('panel', KB_EVAL_PANEL)
  const q = (options.prefillQuery ?? '').trim()
  if (q) params.set(KB_EVAL_PREFILL_QUERY_PARAM, q)
  if (options.workspaceId != null && Number.isFinite(options.workspaceId) && options.workspaceId > 0) {
    params.set(KB_EVAL_WORKSPACE_ID_PARAM, String(Math.trunc(options.workspaceId)))
  }
  if (options.trialClip) params.set(KB_EVAL_TRIAL_CLIP_PARAM, '1')
  return params
}

export function buildKbEvalLobbyPath(options: KbEvalLobbyLinkOptions): string {
  const qs = buildKbEvalLobbySearchParams(options).toString()
  return qs ? `/?${qs}` : '/'
}

export function parseKbEvalDeepLink(searchParams: URLSearchParams): {
  prefillQuery: string | null
  workspaceId: number | null
  trialClip: boolean
} {
  const prefillQuery = searchParams.get(KB_EVAL_PREFILL_QUERY_PARAM)?.trim() || null
  const wsRaw = searchParams.get(KB_EVAL_WORKSPACE_ID_PARAM)
  const workspaceId =
    wsRaw != null && Number.isFinite(Number(wsRaw)) && Number(wsRaw) > 0 ? Math.trunc(Number(wsRaw)) : null
  const trialClip = searchParams.get(KB_EVAL_TRIAL_CLIP_PARAM) === '1'
  return { prefillQuery, workspaceId, trialClip }
}
