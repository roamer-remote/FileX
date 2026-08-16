import type { MqQueueStatus } from '@/api/admin'
import { mqBacklogBreakdown } from '@/utils/mqQueueMetrics'

export type WorkshopKey = 'extract' | 'index' | 'post'

export type WorkshopHealth = 'idle' | 'running' | 'backlog' | 'attention'

export const WORKSHOP_PIPELINE_LABELS: Record<
  WorkshopKey,
  { main: string; retry: string; dlq: string; routeKey: string }
> = {
  extract: { main: 'extract_main', retry: 'extract_retry', dlq: 'extract_dlq', routeKey: 'kb.extract' },
  index: { main: 'index_main', retry: 'index_retry', dlq: 'index_dlq', routeKey: 'kb.index' },
  post: { main: 'post_main', retry: 'post_retry', dlq: 'post_dlq', routeKey: 'kb.post' },
}

export const SIDECAR_LABELS = ['index_notify', 'post_notify', 'mineru_main', 'docling_main'] as const

export function queueByLabelMap(queues: MqQueueStatus[]): Map<string, MqQueueStatus> {
  return new Map(queues.map((q) => [q.label, q]))
}

export function workshopHealth(
  main?: MqQueueStatus,
  retry?: MqQueueStatus,
  dlq?: MqQueueStatus,
): WorkshopHealth {
  if (!main?.online || !retry?.online || !dlq?.online) return 'attention'
  if (main.consumer_busy) return 'running'
  const mainBacklog = main ? mqBacklogBreakdown(main) : { total: 0, queued: 0, running: 0 }
  if (mainBacklog.total > 0 || (main?.message_count ?? 0) > 0) return 'backlog'
  if ((retry?.message_count ?? 0) > 0 || (dlq?.message_count ?? 0) > 0) return 'attention'
  return 'idle'
}

export function packageDisplayCount(main?: MqQueueStatus): number {
  if (!main) return 0
  const backlog = mqBacklogBreakdown(main)
  return Math.max(main.message_count ?? 0, backlog.queued, backlog.total)
}

/** 支线卡片底部三列：未完成 / 排队 / 处理中（含纯 MQ 深度的 notify 队列） */
export function sidecarMetricsDisplay(q: MqQueueStatus): { total: number; queued: number; running: number } {
  const breakdown = mqBacklogBreakdown(q)
  const mqDepth = q.message_count ?? 0

  if (breakdown.total > 0 || breakdown.queued > 0 || breakdown.running > 0) {
    return {
      total: Math.max(breakdown.total, mqDepth),
      queued: breakdown.queued,
      running: breakdown.running,
    }
  }

  if (q.consumer_busy) {
    return { total: Math.max(mqDepth, 1), queued: 0, running: 1 }
  }

  return { total: mqDepth, queued: mqDepth, running: 0 }
}
