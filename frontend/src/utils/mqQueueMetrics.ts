import type { MqQueueStatus } from '@/api/admin'

export function mqMainQueueBacklog(q: {
  backlog_total?: number
  jobs_pending?: number
}): number {
  if (q.backlog_total != null && q.backlog_total >= 0) return q.backlog_total
  return q.jobs_pending ?? 0
}

/** 侧栏/监控：未完成 = queued + running（按 file 去重）；排队/处理中为展示拆分。 */
export function mqBacklogBreakdown(q: {
  backlog_total?: number
  jobs_pending?: number
}): { total: number; queued: number; running: number } {
  const total = mqMainQueueBacklog(q)
  const queued = Math.max(0, q.jobs_pending ?? 0)
  const running = Math.max(0, total - queued)
  return { total, queued, running }
}

export function shouldShowMqWaiting(
  q: MqQueueStatus,
  opts?: { ignoreMessageCount?: boolean },
): boolean {
  const backlog = mqMainQueueBacklog(q) > 0
  const mqDepth = !opts?.ignoreMessageCount && (q.message_count ?? 0) > 0
  return !q.consumer_busy && (backlog || mqDepth)
}
