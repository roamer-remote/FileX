import type { TFunction } from 'i18next'
import type { EChartsOption } from 'echarts'
import type { PipelineKpiMetric, PipelineStageAvgMs } from '@/api/admin'
import { echartsTooltipChrome } from '@/lib/chartTooltipStyle'

export const STAGE_MS_FIELDS = [
  'extract_provider_ms',
  'extract_persist_ms',
  'index_embed_ms',
  'index_persist_ms',
  'index_post_ms',
] as const

export type StageMsField = (typeof STAGE_MS_FIELDS)[number]

export const STAGE_MS_I18N_KEYS: Record<StageMsField, string> = {
  extract_provider_ms: 'admin.settings.pipelineMonitorStageExtractProvider',
  extract_persist_ms: 'admin.settings.pipelineMonitorStageExtractPersist',
  index_embed_ms: 'admin.settings.pipelineMonitorStageIndexEmbed',
  index_persist_ms: 'admin.settings.pipelineMonitorStageIndexPersist',
  index_post_ms: 'admin.settings.pipelineMonitorStageIndexPost',
}

export type StageMsEntry = { key: StageMsField; ms: number }

export function collectStageMsEntries(avg: PipelineStageAvgMs): StageMsEntry[] {
  return STAGE_MS_FIELDS.flatMap((key) => {
    const ms = avg[key]
    return ms != null ? [{ key, ms }] : []
  })
}

export function hasAnyStageMs(avg: PipelineStageAvgMs): boolean {
  return STAGE_MS_FIELDS.some((key) => avg[key] != null)
}

export type ThroughputCounts = {
  extractDone: number
  extractFail: number
  indexDone: number
  indexFail: number
}

export function throughputFromKpis(kpis: PipelineKpiMetric[]): ThroughputCounts {
  const map = Object.fromEntries(kpis.map((kpi) => [kpi.key, kpi.value]))
  return {
    extractDone: map.extract_done_24h ?? 0,
    extractFail: map.extract_failures_24h ?? 0,
    indexDone: map.index_done_24h ?? 0,
    indexFail: map.index_failures_24h ?? 0,
  }
}

function chartThemeColors() {
  const root = document.documentElement
  const cs = getComputedStyle(root)
  return {
    isDark: root.getAttribute('data-theme') === 'dark',
    ink: cs.getPropertyValue('--text-primary').trim() || '#1d1d1f',
    muted: cs.getPropertyValue('--text-muted').trim() || '#6e6e73',
    grid: cs.getPropertyValue('--border-subtle').trim() || 'rgba(0,0,0,0.08)',
  }
}

export function buildThroughputBarOption(
  counts: ThroughputCounts,
  t: TFunction,
): EChartsOption {
  const { isDark, ink, muted, grid } = chartThemeColors()
  const reducedMotion =
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

  return {
    animation: !reducedMotion,
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      ...echartsTooltipChrome(isDark),
    },
    legend: {
      top: 0,
      textStyle: { color: muted, fontSize: 11 },
    },
    xAxis: {
      type: 'category',
      data: [t('admin.settings.pipelineMonitorChartAxisExtract'), t('admin.settings.pipelineMonitorChartAxisIndex')],
      axisLabel: { color: muted, fontSize: 11 },
      axisLine: { lineStyle: { color: grid } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: grid } },
    },
    series: [
      {
        name: t('admin.settings.pipelineMonitorChartSeriesDone'),
        type: 'bar',
        barGap: 0,
        itemStyle: { color: isDark ? '#3d9468' : '#2d7a52', borderRadius: [3, 3, 0, 0] },
        data: [counts.extractDone, counts.indexDone],
      },
      {
        name: t('admin.settings.pipelineMonitorChartSeriesFail'),
        type: 'bar',
        itemStyle: { color: isDark ? '#c45c5c' : '#cf4c4c', borderRadius: [3, 3, 0, 0] },
        data: [counts.extractFail, counts.indexFail],
      },
    ],
    textStyle: { color: ink },
  }
}

export function buildStageMsBarOption(
  entries: StageMsEntry[],
  t: TFunction,
): EChartsOption | null {
  if (entries.length === 0) return null

  const { isDark, ink, muted, grid } = chartThemeColors()
  const reducedMotion =
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

  return {
    animation: !reducedMotion,
    grid: { left: 56, right: 16, top: 16, bottom: 48 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      ...echartsTooltipChrome(isDark),
      valueFormatter: (value) => `${value} ms`,
    },
    xAxis: {
      type: 'category',
      data: entries.map((entry) => t(STAGE_MS_I18N_KEYS[entry.key])),
      axisLabel: { color: muted, fontSize: 10, rotate: 24, interval: 0 },
      axisLine: { lineStyle: { color: grid } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: grid } },
    },
    series: [
      {
        type: 'bar',
        data: entries.map((entry) => entry.ms),
        itemStyle: {
          color: isDark ? '#4a8fd4' : '#0071e3',
          borderRadius: [3, 3, 0, 0],
        },
        label: {
          show: true,
          position: 'top',
          color: muted,
          fontSize: 10,
          formatter: ({ value }) => `${value}`,
        },
      },
    ],
    textStyle: { color: ink },
  }
}
