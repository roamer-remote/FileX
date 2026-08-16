import { describe, expect, it } from 'vitest'
import {
  STAGE_MS_FIELDS,
  STAGE_MS_I18N_KEYS,
  collectStageMsEntries,
  hasAnyStageMs,
  throughputFromKpis,
} from './kbPipelineMonitorCharts'

describe('kbPipelineMonitorCharts', () => {
  it('defines all five stage ms fields with i18n keys', () => {
    expect(STAGE_MS_FIELDS).toHaveLength(5)
    expect(STAGE_MS_FIELDS).toEqual([
      'extract_provider_ms',
      'extract_persist_ms',
      'index_embed_ms',
      'index_persist_ms',
      'index_post_ms',
    ])
    for (const key of STAGE_MS_FIELDS) {
      expect(STAGE_MS_I18N_KEYS[key]).toMatch(/^admin\.settings\.pipelineMonitorStage/)
    }
  })

  it('collectStageMsEntries preserves every present stage field', () => {
    const entries = collectStageMsEntries({
      extract_provider_ms: 1200,
      extract_persist_ms: 80,
      index_embed_ms: 900,
      index_persist_ms: 40,
      index_post_ms: 15,
    })
    expect(entries.map((entry) => entry.key)).toEqual(STAGE_MS_FIELDS)
    expect(entries.map((entry) => entry.ms)).toEqual([1200, 80, 900, 40, 15])
  })

  it('hasAnyStageMs is false only when all five fields are empty', () => {
    expect(hasAnyStageMs({})).toBe(false)
    expect(hasAnyStageMs({ index_post_ms: 12 })).toBe(true)
  })

  it('throughputFromKpis maps completion and failure KPI keys', () => {
    expect(
      throughputFromKpis([
        { key: 'extract_done_24h', value: 10, warning: false },
        { key: 'extract_failures_24h', value: 2, warning: true },
        { key: 'index_done_24h', value: 8, warning: false },
        { key: 'index_failures_24h', value: 1, warning: true },
      ]),
    ).toEqual({
      extractDone: 10,
      extractFail: 2,
      indexDone: 8,
      indexFail: 1,
    })
  })
})
