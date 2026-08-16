import { describe, expect, it } from 'vitest'
import type { AgentRunEvent } from '@/api/agentRuns'
import {
  buildSearchTraceSteps,
  eventHasSearchTraceDrill,
  parseCoverageReceiptTrace,
  parseSearchTraceSummary,
} from './agentRunSearchTrace'

const t = (key: string, opts?: Record<string, unknown>) => {
  if (opts) return `${key}:${JSON.stringify(opts)}`
  return key
}

function ev(partial: Partial<AgentRunEvent> & Pick<AgentRunEvent, 'seq' | 'node_id' | 'phase'>): AgentRunEvent {
  return {
    attempt: 1,
    ts: '2026-07-03T00:00:00+08:00',
    layer: 'tool',
    label: '检索 API',
    ...partial,
  }
}

describe('agentRunSearchTrace', () => {
  it('detects drillable search end events with summary', () => {
    const event = ev({
      seq: 3,
      node_id: 'search',
      phase: 'end',
      meta_json: {
        hit_count: 2,
        search_trace_summary: { hit_count: 2, vector: { merged_unique: 10, after_min_score: 4 } },
      },
    })
    expect(eventHasSearchTraceDrill(event)).toBe(true)
  })

  it('ignores search events without summary', () => {
    const event = ev({ seq: 1, node_id: 'search', phase: 'end', meta_json: { hit_count: 1 } })
    expect(eventHasSearchTraceDrill(event)).toBe(false)
  })

  it('detects coverage receipts emitted by the assess node', () => {
    const event = ev({
      seq: 4,
      node_id: 'assess',
      phase: 'end',
      meta_json: {
        coverage_receipt: {
          version: 'v1',
          answerable: false,
          selected_file_ids: [101, 102],
          selected_section_locators: [{ file_id: 101, chunk_id: 9, heading_path: '工作经历 / 世范软件' }],
          full_md_file_ids: [101],
          insufficient_reasons: ['relation_evidence_insufficient'],
          dimensions: [],
        },
      },
    })

    expect(eventHasSearchTraceDrill(event)).toBe(true)
    expect(parseCoverageReceiptTrace(event.meta_json)).toMatchObject({
      version: 'v1',
      answerable: false,
      selected_file_ids: [101, 102],
      full_md_file_ids: [101],
      insufficient_reasons: ['relation_evidence_insufficient'],
    })
  })

  it('builds L3 vector rerank sag steps', () => {
    const summary = parseSearchTraceSummary({
      search_trace_summary: {
        hit_count: 5,
        vector: { merged_unique: 20, after_min_score: 8 },
        rerank: { after_rerank: 8, rerank_applied: true },
        sag: { query_entities: 2, seed_events: 3, hop_expanded: 6, added_hits: 1 },
        timings_ms: { vector: 12.5 },
      },
    })
    expect(summary).not.toBeNull()
    const steps = buildSearchTraceSteps(summary!, t)
    expect(steps.map((s) => s.id)).toEqual(['vector', 'rerank', 'sag'])
  })
})
