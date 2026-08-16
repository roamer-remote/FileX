import api from './index'

export interface MqUserActiveTask {
  kind: string
  file_id?: number
  filename?: string | null
  progress_pct?: number | null
  progress_stage?: string | null
  progress_detail?: string | null
  /** 当前活动流程实际使用的模型；不包含任何凭证。 */
  model?: string | null
}

/** Admin WS includes username; user WS omits it. */
export function mqActiveTaskUsername(task: MqUserActiveTask): string | undefined {
  const username = (task as { username?: string }).username
  return typeof username === 'string' && username.length > 0 ? username : undefined
}

export interface MqUserQueuedJobItem {
  job_id: number
  file_id: number
  filename: string
  updated_at: string | null
}

export interface MqUserQueuedJobsResponse {
  total: number
  items: MqUserQueuedJobItem[]
  truncated: boolean
}

export interface MqUserJobCancelResponse {
  job_id: number
  file_id: number
  kind: string
  mq_removed: number
}

export function getUserMqIndexQueuedJobs(limit = 50) {
  return api.get<MqUserQueuedJobsResponse>('/mq/queued-jobs', { params: { limit } })
}

export function getUserMqExtractQueuedJobs(limit = 50) {
  return api.get<MqUserQueuedJobsResponse>('/mq/extract-queued-jobs', { params: { limit } })
}

export function getUserMqPostQueuedJobs(limit = 50) {
  return api.get<MqUserQueuedJobsResponse>('/mq/post-queued-jobs', { params: { limit } })
}

export function cancelUserMqIndexJob(jobId: number) {
  return api.post<MqUserJobCancelResponse>(`/mq/index-jobs/${jobId}/cancel`)
}

export function cancelUserMqExtractJob(jobId: number) {
  return api.post<MqUserJobCancelResponse>(`/mq/extract-jobs/${jobId}/cancel`)
}

export type UserMqMessageQueueLabel =
  | 'index_retry'
  | 'index_dlq'
  | 'post_retry'
  | 'post_dlq'
  | 'extract_retry'
  | 'extract_dlq'

export interface MqUserQueueMessageItem {
  index: number
  job_id: number | null
  last_error: string | null
  body_preview: string
  duplicate_count?: number
}

export interface MqUserQueueMessagesResponse {
  queue_label: string
  total: number
  peek_count: number
  items: MqUserQueueMessageItem[]
  truncated: boolean
}

export function getUserMqQueueMessages(queue: UserMqMessageQueueLabel, limit = 50) {
  return api.get<MqUserQueueMessagesResponse>('/mq/queue-messages', { params: { queue, limit } })
}

export function removeUserMqQueueMessage(queueLabel: UserMqMessageQueueLabel, jobId: number) {
  return api.post<{ queue_label: string; removed: number }>('/mq/queue-messages/remove', {
    queue_label: queueLabel,
    job_id: jobId,
  })
}
