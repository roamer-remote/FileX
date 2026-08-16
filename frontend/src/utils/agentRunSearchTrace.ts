import type { AgentRunEvent } from '@/api/agentRuns'

export type SearchTraceSummary = {
  hit_count?: number
  vector?: {
    vector_candidates?: number | null
    fts_candidates?: number | null
    merged_unique?: number | null
    after_acl_filter?: number | null
    after_min_score?: number | null
    after_mmr?: number | null
  }
  rerank?: {
    after_rerank?: number | null
    rerank_applied?: boolean | null
  }
  sag?: {
    query_entities?: number | null
    seed_events?: number | null
    hop_expanded?: number | null
    reranked_events?: number | null
    expanded?: boolean | null
    added_hits?: number | null
  }
  timings_ms?: Record<string, number>
}

export type SearchTraceStep = {
  id: 'vector' | 'rerank' | 'sag'
  labelKey: string
  detail?: string
  ms?: number
}

const SEARCH_DRILL_NODE_IDS = new Set(['search', 'kb_search'])

export type CoverageReceiptTrace = {
  version?: string
  answerable?: boolean
  selected_file_ids: number[]
  selected_section_locators: Array<{
    file_id: number
    chunk_id?: number
    heading_path?: string
  }>
  full_md_file_ids: number[]
  insufficient_reasons: string[]
  dimensions: Array<Record<string, unknown>>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function numberList(value: unknown): number[] {
  return Array.isArray(value)
    ? value.filter((item): item is number => typeof item === 'number' && Number.isFinite(item))
    : []
}

export function parseCoverageReceiptTrace(
  meta: Record<string, unknown> | null | undefined,
): CoverageReceiptTrace | null {
  const raw = meta?.coverage_receipt
  if (!isRecord(raw)) return null
  const locators = Array.isArray(raw.selected_section_locators)
    ? raw.selected_section_locators.flatMap((locator) => {
        if (!isRecord(locator) || typeof locator.file_id !== 'number') return []
        return [{
          file_id: locator.file_id,
          ...(typeof locator.chunk_id === 'number' ? { chunk_id: locator.chunk_id } : {}),
          ...(typeof locator.heading_path === 'string' ? { heading_path: locator.heading_path } : {}),
        }]
      })
    : []
  return {
    ...(typeof raw.version === 'string' ? { version: raw.version } : {}),
    ...(typeof raw.answerable === 'boolean' ? { answerable: raw.answerable } : {}),
    selected_file_ids: numberList(raw.selected_file_ids),
    selected_section_locators: locators,
    full_md_file_ids: numberList(raw.full_md_file_ids),
    insufficient_reasons: Array.isArray(raw.insufficient_reasons)
      ? raw.insufficient_reasons.filter((reason): reason is string => typeof reason === 'string')
      : [],
    dimensions: Array.isArray(raw.dimensions)
      ? raw.dimensions.filter(isRecord)
      : [],
  }
}

export function parseSearchTraceSummary(meta: Record<string, unknown> | null | undefined): SearchTraceSummary | null {
  const raw = meta?.search_trace_summary
  if (!raw || typeof raw !== 'object') return null
  return raw as SearchTraceSummary
}

export function eventHasSearchTraceDrill(event: AgentRunEvent): boolean {
  if (event.phase !== 'end') return false
  return (
    (SEARCH_DRILL_NODE_IDS.has(event.node_id) && parseSearchTraceSummary(event.meta_json) != null)
    || parseCoverageReceiptTrace(event.meta_json) != null
  )
}

function pickNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

export function buildSearchTraceSteps(summary: SearchTraceSummary, t: (key: string, opts?: Record<string, unknown>) => string): SearchTraceStep[] {
  const steps: SearchTraceStep[] = []
  const vector = summary.vector
  const merged = pickNumber(vector?.merged_unique) ?? pickNumber(vector?.vector_candidates)
  const filtered = pickNumber(vector?.after_min_score) ?? pickNumber(vector?.after_acl_filter)
  steps.push({
    id: 'vector',
    labelKey: 'agentRuns.searchTraceStepVector',
    detail:
      merged != null || filtered != null
        ? t('agentRuns.searchTraceVectorDetail', { merged: merged ?? '—', filtered: filtered ?? '—' })
        : undefined,
    ms: pickNumber(summary.timings_ms?.vector),
  })

  const rerankCount = pickNumber(summary.rerank?.after_rerank)
  steps.push({
    id: 'rerank',
    labelKey: 'agentRuns.searchTraceStepRerank',
    detail:
      rerankCount != null
        ? t('agentRuns.searchTraceRerankDetail', {
            count: rerankCount,
            applied: summary.rerank?.rerank_applied ? t('agentRuns.searchTraceYes') : t('agentRuns.searchTraceNo'),
          })
        : undefined,
    ms: pickNumber(summary.timings_ms?.rerank),
  })

  const sag = summary.sag
  const hasSag =
    sag &&
    (pickNumber(sag.query_entities) ||
      pickNumber(sag.seed_events) ||
      pickNumber(sag.hop_expanded) ||
      sag.expanded)
  if (hasSag) {
    steps.push({
      id: 'sag',
      labelKey: 'agentRuns.searchTraceStepSag',
      detail: t('agentRuns.searchTraceSagDetail', {
        entities: pickNumber(sag?.query_entities) ?? 0,
        seeds: pickNumber(sag?.seed_events) ?? 0,
        hops: pickNumber(sag?.hop_expanded) ?? 0,
        added: pickNumber(sag?.added_hits) ?? 0,
      }),
      ms: pickNumber(summary.timings_ms?.sag_expand),
    })
  }

  return steps
}
