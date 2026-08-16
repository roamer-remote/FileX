import type { WorkshopKey } from './mqFactoryMetrics'

export type MqFactoryDesignTheme = 'light' | 'dark'

const BASE = '/assets/mq-factory'

export function workshopRowImage(workshop: WorkshopKey, theme: MqFactoryDesignTheme): string {
  return `${BASE}/${theme}/workshop-${workshop}.png`
}

export function sidecarsImage(theme: MqFactoryDesignTheme): string {
  return `${BASE}/${theme}/sidecars.png`
}

/** 1496×232 车间行 SSOT；数值为百分比定位 */
export const WORKSHOP_ROW_LAYOUT = {
  refWidth: 1496,
  refHeight: 232,
  metrics: {
    total: { left: 9.5, top: 38 },
    queued: { left: 9.5, top: 48 },
    running: { left: 9.5, top: 58 },
  },
  counters: {
    queue: { left: 20.5, top: 82 },
    process: { left: 37.2, top: 82 },
    retry: { left: 53.8, top: 82 },
    dlq: { left: 70.5, top: 82 },
  },
  hits: {
    queue: { left: 14, top: 22, width: 17, height: 68 },
    process: { left: 33, top: 22, width: 17, height: 68 },
    retry: { left: 52, top: 22, width: 17, height: 68 },
    dlq: { left: 71, top: 22, width: 17, height: 68 },
    expand: { left: 86, top: 2, width: 12, height: 14 },
  },
  bubble: { left: 33, top: 0, width: 34, minTop: 2 },
  healthBadge: { left: 28, top: 8.5, width: 12, height: 8 },
} as const

/** 1496×162 支线区 */
export const SIDECAR_LAYOUT = {
  refWidth: 1496,
  refHeight: 162,
  cards: [
    { left: 1.5, width: 23, metricsTop: 78 },
    { left: 26, width: 23, metricsTop: 78 },
    { left: 50.5, width: 23, metricsTop: 78 },
    { left: 75, width: 23, metricsTop: 78 },
  ],
  hits: [
    { left: 1.5, top: 18, width: 23, height: 78 },
    { left: 26, top: 18, width: 23, height: 78 },
    { left: 50.5, top: 18, width: 23, height: 78 },
    { left: 75, top: 18, width: 23, height: 78 },
  ],
} as const

export function useMqFactoryDesignTheme(): MqFactoryDesignTheme {
  if (typeof document === 'undefined') return 'light'
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
}
