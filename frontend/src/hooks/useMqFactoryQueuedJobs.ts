import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getAdminMqExtractQueuedJobs,
  getAdminMqPostQueuedJobs,
  getAdminMqQueuedJobs,
  type MqQueueStatus,
} from '@/api/admin'
import {
  getUserMqExtractQueuedJobs,
  getUserMqIndexQueuedJobs,
  getUserMqPostQueuedJobs,
} from '@/api/mq'
import type { WorkshopKey } from '@/components/mq/factory/mqFactoryMetrics'
import { WORKSHOP_PIPELINE_LABELS } from '@/components/mq/factory/mqFactoryMetrics'

export type MqFactoryQueuedItem = {
  job_id: number
  file_id: number
  filename: string
  updated_at: string | null
  username?: string
}

export type MqFactoryQueuedPreview = {
  total: number
  items: MqFactoryQueuedItem[]
}

const EMPTY: MqFactoryQueuedPreview = { total: 0, items: [] }

const POLL_MS = 5000

async function fetchWorkshopQueued(
  mode: 'admin' | 'user',
  workshopKey: WorkshopKey,
  limit: number,
): Promise<MqFactoryQueuedPreview> {
  const fetcher =
    mode === 'admin'
      ? workshopKey === 'extract'
        ? getAdminMqExtractQueuedJobs
        : workshopKey === 'post'
          ? getAdminMqPostQueuedJobs
          : getAdminMqQueuedJobs
      : workshopKey === 'extract'
        ? getUserMqExtractQueuedJobs
        : workshopKey === 'post'
          ? getUserMqPostQueuedJobs
          : getUserMqIndexQueuedJobs
  const res = await fetcher(limit)
  const items: MqFactoryQueuedItem[] = res.data.items.map((item) => {
    const row: MqFactoryQueuedItem = {
      job_id: item.job_id,
      file_id: item.file_id,
      filename: item.filename,
      updated_at: item.updated_at ?? null,
    }
    if (mode === 'admin' && 'username' in item && typeof item.username === 'string') {
      row.username = item.username
    }
    return row
  })
  return { total: res.data.total, items }
}

function workshopPendingKey(workshopKey: WorkshopKey, queues: MqQueueStatus[]): string {
  const label = WORKSHOP_PIPELINE_LABELS[workshopKey].main
  const main = queues.find((q) => q.label === label)
  return `${main?.jobs_pending ?? 0}:${main?.backlog_total ?? 0}`
}

export function useMqFactoryQueuedJobs(
  sortedQueues: MqQueueStatus[],
  mode: 'admin' | 'user',
  enabled = true,
): Record<WorkshopKey, MqFactoryQueuedPreview> {
  const [previews, setPreviews] = useState<Record<WorkshopKey, MqFactoryQueuedPreview>>({
    extract: EMPTY,
    index: EMPTY,
    post: EMPTY,
  })
  const loadSeq = useRef(0)
  const pendingKey = `${workshopPendingKey('extract', sortedQueues)}|${workshopPendingKey('index', sortedQueues)}|${workshopPendingKey('post', sortedQueues)}`

  const loadAll = useCallback(async () => {
    if (!enabled) return
    const seq = ++loadSeq.current
    try {
      const [extract, index, post] = await Promise.all([
        fetchWorkshopQueued(mode, 'extract', 10),
        fetchWorkshopQueued(mode, 'index', 10),
        fetchWorkshopQueued(mode, 'post', 10),
      ])
      if (seq !== loadSeq.current) return
      setPreviews({ extract, index, post })
    } catch {
      if (seq !== loadSeq.current) return
    }
  }, [mode, enabled])

  useEffect(() => {
    if (!enabled) return
    void loadAll()
  }, [loadAll, pendingKey, enabled])

  useEffect(() => {
    if (!enabled) return
    const timer = window.setInterval(() => {
      void loadAll()
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [loadAll, enabled])

  return previews
}
