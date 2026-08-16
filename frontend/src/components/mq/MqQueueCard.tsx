import { CheckCircleOutlined, CloseCircleOutlined, EyeOutlined, LoadingOutlined } from '@ant-design/icons'
import { Button, Tag, Tooltip } from 'antd'
import { mqActiveTaskUsername, type MqUserActiveTask } from '@/api/mq'
import MqStorageFilenameCell from '@/components/MqStorageFilenameCell'
import { mqBacklogBreakdown, mqMainQueueBacklog } from '@/utils/mqQueueMetrics'

export const ADMIN_QUEUE_GROUPS = [
  {
    key: 'extract',
    titleKey: 'admin.mq.groupExtract',
    labels: ['extract_main', 'extract_retry', 'extract_dlq'],
  },
  {
    key: 'index',
    titleKey: 'admin.mq.groupIndex',
    labels: ['index_main', 'index_retry', 'index_dlq'],
  },
  {
    key: 'post',
    titleKey: 'admin.mq.groupPost',
    labels: ['post_main', 'post_retry', 'post_dlq'],
  },
  {
    key: 'other',
    titleKey: 'admin.mq.groupOther',
    labels: ['index_notify', 'post_notify', 'mineru_main', 'docling_main', 'gpu_mineru', 'gpu_raptor'],
  },
] as const

export const USER_QUEUE_GROUPS = [
  {
    key: 'extract',
    titleKey: 'admin.mq.groupExtract',
    labels: ['extract_main', 'extract_retry', 'extract_dlq'],
  },
  {
    key: 'index',
    titleKey: 'admin.mq.groupIndex',
    labels: ['index_main', 'index_retry', 'index_dlq'],
  },
  {
    key: 'post',
    titleKey: 'admin.mq.groupPost',
    labels: ['post_main', 'post_retry', 'post_dlq'],
  },
] as const

export const USER_MQ_MESSAGE_LABELS = new Set([
  'index_retry',
  'index_dlq',
  'post_retry',
  'post_dlq',
  'extract_retry',
  'extract_dlq',
])

const QUEUE_DISPLAY_ORDER = ADMIN_QUEUE_GROUPS.flatMap((g) => g.labels)

export const LABEL_TO_TASK_KIND: Record<string, string> = {
  index_main: 'kb_index',
  post_main: 'kb_post',
  extract_main: 'kb_extract',
  mineru_main: 'kb_mineru',
  docling_main: 'kb_docling',
}

const BACKLOG_LABELS = new Set(['index_main', 'post_main', 'extract_main'])

export type MainQueueDbSource = 'index' | 'post' | 'extract' | null

export function mainQueueDbSource(label?: string): MainQueueDbSource {
  if (label === 'index_main') return 'index'
  if (label === 'post_main') return 'post'
  if (label === 'extract_main') return 'extract'
  return null
}

export function queueSortIndex(label: string): number {
  const i = QUEUE_DISPLAY_ORDER.indexOf(label as (typeof QUEUE_DISPLAY_ORDER)[number])
  return i === -1 ? 99 : i
}

export function formatMqUpdatedAt(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function MqQueueWaveBackdrop() {
  const wave =
    'M0,30 C40,14 80,46 120,30 160,14 200,46 240,30 280,14 320,30 L320,64 L0,64 Z' +
    'M320,30 C360,14 400,46 440,30 480,14 520,46 560,30 600,14 640,30 L640,64 L320,64 Z'
  const wave2 =
    'M0,36 C53,20 107,52 160,36 213,20 267,52 320,36 L320,64 L0,64 Z' +
    'M320,36 C373,20 427,52 480,36 533,20 587,52 640,36 L640,64 L320,64 Z'
  return (
    <div className="mq-queue-wave" aria-hidden>
      <svg className="mq-queue-wave-layer mq-queue-wave-layer--deep" viewBox="0 0 640 64" preserveAspectRatio="none">
        <path d={wave} />
      </svg>
      <svg className="mq-queue-wave-layer mq-queue-wave-layer--crest" viewBox="0 0 640 64" preserveAspectRatio="none">
        <path d={wave2} />
      </svg>
    </div>
  )
}

export function mqQueueTitle(label: string, t: (k: string, opts?: Record<string, unknown>) => string): string {
  switch (label) {
    case 'index_main':
      return t('admin.mq.indexMainQueue')
    case 'index_retry':
      return t('admin.mq.indexRetryQueue')
    case 'index_dlq':
      return t('admin.mq.indexDlq')
    case 'index_notify':
      return t('admin.mq.notifyQueue')
    case 'post_main':
      return t('admin.mq.postMainQueue')
    case 'post_retry':
      return t('admin.mq.postRetryQueue')
    case 'post_dlq':
      return t('admin.mq.postDlq')
    case 'post_notify':
      return t('admin.mq.postNotifyQueue')
    case 'extract_main':
      return t('admin.mq.extractMainQueue')
    case 'extract_retry':
      return t('admin.mq.extractRetryQueue')
    case 'extract_dlq':
      return t('admin.mq.extractDlq')
    case 'mineru_main':
      return t('admin.mq.mineruMainQueue')
    case 'docling_main':
      return t('admin.mq.doclingMainQueue')
    case 'gpu_mineru':
      return t('admin.mq.gpuMineruMainQueue')
    case 'gpu_raptor':
      return t('admin.mq.gpuRaptorMainQueue')
    default:
      return label
  }
}

export type MqQueueCardQueue = {
  name: string
  label?: string
  online: boolean
  message_count: number
  consumer_count: number
  consumer_busy?: boolean
  jobs_pending?: number
  backlog_total?: number
}

type MqQueueCardProps = {
  q: MqQueueCardQueue
  title: string
  t: (k: string, opts?: Record<string, unknown>) => string
  activeTasks: MqUserActiveTask[]
  mode?: 'admin' | 'user'
  onViewMessages: (
    queueName: string,
    queueLabel: string,
    queueKey: string,
    dbSource: MainQueueDbSource,
  ) => void
}

export default function MqQueueCard({
  q,
  title,
  t,
  activeTasks,
  mode = 'admin',
  onViewMessages,
}: MqQueueCardProps) {
  const isUser = mode === 'user'
  const isUserMqMessageQueue = q.label ? USER_MQ_MESSAGE_LABELS.has(q.label) : false
  const taskKind = q.label ? LABEL_TO_TASK_KIND[q.label] : undefined
  const queueTasks = taskKind ? activeTasks.filter((task) => task.kind === taskKind) : []
  const hasBacklog = q.label ? BACKLOG_LABELS.has(q.label) : false
  const backlog = mqBacklogBreakdown(q)
  const showWaiting =
    hasBacklog &&
    !q.consumer_busy &&
    (isUser
      ? backlog.queued > 0 || backlog.total > 0
      : mqMainQueueBacklog(q) > 0 || (q.message_count ?? 0) > 0)
  const isRunning = !!q.consumer_busy
  const canView = isUser
    ? (hasBacklog &&
        q.online &&
        (backlog.total > 0 || (q.jobs_pending ?? 0) > 0 || queueTasks.length > 0)) ||
      (isUserMqMessageQueue && q.online && mqMainQueueBacklog(q) > 0)
    : q.online &&
      ((q.message_count ?? 0) > 0 ||
        (hasBacklog && ((q.jobs_pending ?? 0) > 0 || queueTasks.length > 0)))
  const toneClass = q.label ? `mq-queue-card--${q.label}` : ''
  const cardClass = ['mq-queue-card', toneClass, isRunning ? 'mq-queue-card--running' : ''].filter(Boolean).join(' ')

  return (
    <div className={cardClass}>
      {isRunning ? <MqQueueWaveBackdrop /> : null}
      <div className="mq-queue-top">
        <div className="mq-queue-ident">
          <div className="mq-queue-title-row">
            <span className="mq-queue-title">{title}</span>
            {!isUser ? (
              <span className="mq-metric mq-queue-consumers">
                <span className="mq-metric-label">{t('admin.mq.consumers')}</span>
                <span className="mq-metric-value mq-metric-value--inline">
                  {q.consumer_count}
                  {showWaiting ? (
                    <Tag className="mq-running-tag" color="warning">
                      {t('admin.mq.consumerWaiting')}
                    </Tag>
                  ) : null}
                  {q.consumer_busy ? (
                    <Tag className="mq-running-tag" color="processing" icon={<LoadingOutlined spin />}>
                      {t('admin.mq.consumerRunning')}
                    </Tag>
                  ) : null}
                </span>
              </span>
            ) : q.consumer_busy ? (
              <Tag className="mq-running-tag" color="processing" icon={<LoadingOutlined spin />}>
                {t('admin.mq.consumerRunning')}
              </Tag>
            ) : showWaiting ? (
              <Tag className="mq-running-tag" color="warning">
                {t('admin.mq.consumerWaiting')}
              </Tag>
            ) : null}
          </div>
          {!isUser ? <code className="mq-queue-name">{q.name}</code> : null}
        </div>
        <Tooltip title={q.online ? t('admin.mq.online') : t('admin.mq.offline')}>
          <span
            className={`mq-queue-status-icon${q.online ? ' is-online' : ' is-offline'}`}
            role="img"
            aria-label={q.online ? t('admin.mq.online') : t('admin.mq.offline')}
          >
            {q.online ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
          </span>
        </Tooltip>
      </div>
      {taskKind && queueTasks.length > 0 ? (
        <div className="mq-queue-active">
          {queueTasks.slice(0, 3).map((task) => (
            <div
              key={`${task.kind}-${task.file_id}-${mqActiveTaskUsername(task) ?? '?'}`}
              className="mq-queue-active-row"
            >
              {!isUser ? (
                <span className="mq-queue-active-user">{mqActiveTaskUsername(task) ?? '—'}</span>
              ) : null}
              <span className={`mq-queue-active-file${isUser ? ' mq-queue-active-file--solo' : ''}`}>
                <MqStorageFilenameCell filename={task.filename || `#${task.file_id ?? '?'}`} />
              </span>
            </div>
          ))}
          {queueTasks.length > 3 ? (
            <span className="mq-queue-active-more">{t('admin.mq.activeTasksMore', { count: queueTasks.length - 3 })}</span>
          ) : null}
        </div>
      ) : null}
      <div className="mq-queue-foot">
        <div className="mq-queue-metrics">
          {hasBacklog ? (
            <>
              <span className="mq-metric">
                <Tooltip title={t('admin.mq.backlogTotalTip')}>
                  <span className="mq-metric-label">{t('admin.mq.backlogTotal')}</span>
                </Tooltip>
                <span className="mq-metric-value">{backlog.total}</span>
              </span>
              <span className="mq-metric-sep" aria-hidden>
                ·
              </span>
              <span className="mq-metric">
                <Tooltip title={t('admin.mq.backlogQueuedTip')}>
                  <span className="mq-metric-label">{t('admin.mq.backlogQueued')}</span>
                </Tooltip>
                <span className="mq-metric-value">{backlog.queued}</span>
              </span>
              <span className="mq-metric-sep" aria-hidden>
                ·
              </span>
              <span className="mq-metric">
                <Tooltip title={t('admin.mq.backlogRunningTip')}>
                  <span className="mq-metric-label">{t('admin.mq.backlogRunning')}</span>
                </Tooltip>
                <span className="mq-metric-value">{backlog.running}</span>
              </span>
            </>
          ) : (
            <span className="mq-metric">
              <span className="mq-metric-label">{t('admin.mq.backlog')}</span>
              <span className="mq-metric-value">{mqMainQueueBacklog(q)}</span>
            </span>
          )}
        </div>
        <Button
          type="link"
          size="small"
          className="mq-queue-view-btn"
          icon={<EyeOutlined />}
          disabled={!canView}
          onClick={() => onViewMessages(q.name, title, q.label ?? '', mainQueueDbSource(q.label))}
        >
          {t(hasBacklog ? 'admin.mq.viewDetails' : 'admin.mq.viewMessages')}
        </Button>
      </div>
    </div>
  )
}

const SIDECAR_TASK_KINDS = new Set(['kb_mineru', 'kb_docling'])

export function MqSidecarActiveTasks({
  activeTasks,
  t,
}: {
  activeTasks: MqUserActiveTask[]
  t: (k: string, opts?: Record<string, unknown>) => string
}) {
  const sidecarTasks = activeTasks.filter((task) => SIDECAR_TASK_KINDS.has(task.kind))
  if (sidecarTasks.length === 0) return null

  function kindLabel(kind: string) {
    if (kind === 'kb_mineru') return t('admin.mq.mineruMainQueue')
    if (kind === 'kb_docling') return t('admin.mq.doclingMainQueue')
    return kind
  }

  return (
    <section className="mq-queue-group mq-queue-group--other" aria-label={t('userMq.sidecarActive')}>
      <h3 className="mq-queue-group-title">{t('userMq.sidecarActive')}</h3>
      <div className="mq-sidecar-active-list">
        {sidecarTasks.map((task) => (
          <div key={`${task.kind}-${task.file_id}`} className="mq-queue-active-row mq-sidecar-active-row">
            <span className="mq-sidecar-active-kind">{kindLabel(task.kind)}</span>
            <span className="mq-queue-active-file mq-queue-active-file--solo">
              <MqStorageFilenameCell filename={task.filename || `#${task.file_id ?? '?'}`} />
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
