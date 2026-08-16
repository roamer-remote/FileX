import type { MqQueueStatus, MqSystemResources } from '@/api/admin'
import type { MqUserActiveTask } from '@/api/mq'
import type { MqFactoryQueuedPreview } from '@/hooks/useMqFactoryQueuedJobs'
import { ADMIN_QUEUE_GROUPS } from '@/components/mq/MqQueueCard'
import type { WorkshopKey } from '@/components/mq/factory/mqFactoryMetrics'

export type EvidenceScene = 'default' | 'progress' | 'multi-queue' | 'extract-running' | 'extract-idle'

function q(
  label: string,
  overrides: Partial<MqQueueStatus> = {},
): MqQueueStatus {
  return {
    name: `q.${label}`,
    label,
    online: true,
    message_count: 0,
    consumer_count: 1,
    consumer_busy: false,
    jobs_pending: 0,
    backlog_total: 0,
    ...overrides,
  }
}

/** 122 evidence：按 scene 切换运行态 / 排队 / progress fixture */
export function buildEvidenceQueues(scene: EvidenceScene = 'default'): MqQueueStatus[] {
  const labels = ADMIN_QUEUE_GROUPS.flatMap((g) => g.labels)
  const byLabel = new Map<string, MqQueueStatus>()

  for (const label of labels) {
    byLabel.set(label, q(label))
  }

  if (scene === 'extract-idle') {
    byLabel.set('extract_main', q('extract_main'))
    byLabel.set('index_main', q('index_main'))
    byLabel.set('post_main', q('post_main'))
  } else if (scene === 'extract-running') {
    byLabel.set(
      'extract_main',
      q('extract_main', {
        consumer_busy: true,
        message_count: 0,
        jobs_pending: 1,
        backlog_total: 1,
      }),
    )
    byLabel.set('index_main', q('index_main', { jobs_pending: 1, backlog_total: 1 }))
    byLabel.set('post_main', q('post_main'))
  } else if (scene === 'progress') {
    byLabel.set(
      'extract_main',
      q('extract_main', { message_count: 2, jobs_pending: 2, backlog_total: 2 }),
    )
    byLabel.set('index_main', q('index_main', { jobs_pending: 1, backlog_total: 1 }))
    byLabel.set(
      'post_main',
      q('post_main', {
        consumer_busy: true,
        message_count: 0,
        jobs_pending: 0,
        backlog_total: 1,
      }),
    )
  } else if (scene === 'multi-queue') {
    byLabel.set(
      'extract_main',
      q('extract_main', { message_count: 2, jobs_pending: 2, backlog_total: 2 }),
    )
    byLabel.set(
      'index_main',
      q('index_main', {
        consumer_busy: true,
        message_count: 0,
        jobs_pending: 4,
        backlog_total: 5,
      }),
    )
    byLabel.set('post_main', q('post_main', { jobs_pending: 0, backlog_total: 0 }))
  } else {
    byLabel.set(
      'extract_main',
      q('extract_main', { message_count: 3, jobs_pending: 3, backlog_total: 3 }),
    )
    byLabel.set('index_main', q('index_main', { jobs_pending: 1, backlog_total: 1 }))
    byLabel.set(
      'post_main',
      q('post_main', {
        consumer_busy: true,
        message_count: 1,
        jobs_pending: 0,
        backlog_total: 1,
      }),
    )
  }

  byLabel.set('post_retry', q('post_retry', scene === 'extract-idle' ? {} : { message_count: 2 }))
  byLabel.set('index_notify', q('index_notify', scene === 'extract-idle' ? {} : { jobs_pending: 4, backlog_total: 4 }))
  byLabel.set('post_notify', q('post_notify', scene === 'extract-idle' ? {} : { consumer_busy: true, backlog_total: 2 }))
  byLabel.set('mineru_main', q('mineru_main', scene === 'extract-idle' ? {} : { jobs_pending: 1, backlog_total: 1 }))
  byLabel.set('docling_main', q('docling_main', { jobs_pending: 0, backlog_total: 0 }))

  return labels.map((label) => byLabel.get(label)!)
}

export function buildEvidenceActiveTasks(scene: EvidenceScene): MqUserActiveTask[] {
  if (scene === 'extract-running') {
    return [
      {
        kind: 'kb_extract',
        file_id: 3001,
        filename: 'illustrated-workshop-sample.pdf',
        progress_stage: '生成笔记',
        progress_pct: 42,
        progress_detail: 'MinerU · 18/43',
        ...( { username: 'alice' } as Record<string, string> ),
      },
    ]
  }
  if (scene === 'progress') {
    return [
      {
        kind: 'kb_post',
        file_id: 1001,
        filename: 'quarterly-report-2026.pdf',
        progress_stage: 'RAPTOR',
        progress_pct: 38,
        progress_detail: '12/32',
        ...( { username: 'demo' } as Record<string, string> ),
      },
    ]
  }
  if (scene === 'multi-queue') {
    return [
      {
        kind: 'kb_index',
        file_id: 2002,
        filename: 'large-knowledge-base.pdf',
        progress_stage: '向量嵌入',
        progress_pct: 42,
        progress_detail: '21/50',
        ...( { username: 'alice' } as Record<string, string> ),
      },
    ]
  }
  return [
    {
      kind: 'kb_post',
      file_id: 1001,
      filename: 'quarterly-report-2026.pdf',
      ...( { username: 'demo' } as Record<string, string> ),
    },
  ]
}

export function buildEvidenceQueuedPreviews(scene: EvidenceScene): Record<WorkshopKey, MqFactoryQueuedPreview> {
  const empty: MqFactoryQueuedPreview = { total: 0, items: [] }
  if (scene === 'extract-running' || scene === 'extract-idle' || scene === 'progress') {
    return { extract: empty, index: empty, post: empty }
  }
  if (scene === 'multi-queue') {
    return {
      extract: {
        total: 2,
        items: [
          { job_id: 11, file_id: 301, filename: 'notes-draft.md', updated_at: null, username: 'bob' },
          { job_id: 12, file_id: 302, filename: 'meeting-minutes.docx', updated_at: null, username: 'carol' },
        ],
      },
      index: {
        total: 4,
        items: [
          { job_id: 21, file_id: 401, filename: 'policy-handbook.pdf', updated_at: null, username: 'dave' },
          { job_id: 22, file_id: 402, filename: 'research-paper.pdf', updated_at: null, username: 'eve' },
          { job_id: 23, file_id: 403, filename: 'training-slides.pptx', updated_at: null, username: 'frank' },
        ],
      },
      post: empty,
    }
  }
  return { extract: empty, index: empty, post: empty }
}

export function buildEvidenceSystemResources(): MqSystemResources {
  return {
    cpu_percent: 72,
    gpu: {
      available: true,
      name: 'NVIDIA RTX 4090',
      util_percent: 86,
      memory_used_mb: 18841,
      memory_total_mb: 24564,
    },
  }
}
