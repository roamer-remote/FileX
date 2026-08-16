import { useEffect, useState } from 'react'
import type { MqUserActiveTask } from '@/api/mq'
import { mqActiveTaskUsername } from '@/api/mq'
import type { MqQueueStatus } from '@/api/admin'
import MqStorageFilenameCell from '@/components/MqStorageFilenameCell'
import {
  LABEL_TO_TASK_KIND,
  mainQueueDbSource,
  mqQueueTitle,
  type MainQueueDbSource,
} from '@/components/mq/MqQueueCard'
import { mqBacklogBreakdown } from '@/utils/mqQueueMetrics'
import {
  packageDisplayCount,
  WORKSHOP_PIPELINE_LABELS,
  type WorkshopHealth,
  type WorkshopKey,
} from './mqFactoryMetrics'
import {
  useMqFactoryDesignTheme,
  WORKSHOP_ROW_LAYOUT,
  workshopRowImage,
} from './mqFactoryDesignLayout'
import './MqFactoryDesign.css'

export type MqWorkshopDisplay = 'inline' | 'expanded'

type MqWorkshopPipelineProps = {
  workshopKey: WorkshopKey
  workshopIndex: number
  main?: MqQueueStatus
  retry?: MqQueueStatus
  dlq?: MqQueueStatus
  health: WorkshopHealth
  activeTasks: MqUserActiveTask[]
  display?: MqWorkshopDisplay
  mode?: 'admin' | 'user'
  showExpand?: boolean
  onExpand?: () => void
  t: (k: string, opts?: Record<string, unknown>) => string
  onViewMessages: (
    queueName: string,
    queueLabel: string,
    queueKey: string,
    dbSource: MainQueueDbSource,
  ) => void
}

const HEALTH_I18N: Record<WorkshopHealth, string> = {
  idle: 'admin.mq.factoryHealthIdle',
  running: 'admin.mq.factoryHealthRunning',
  backlog: 'admin.mq.factoryHealthBacklog',
  attention: 'admin.mq.factoryHealthAttention',
}

const TITLE_KEYS: Record<WorkshopKey, string> = {
  extract: 'admin.mq.groupExtract',
  index: 'admin.mq.groupIndex',
  post: 'admin.mq.groupPost',
}

function pct(v: number) {
  return `${v}%`
}

function openQueue(
  q: MqQueueStatus | undefined,
  t: MqWorkshopPipelineProps['t'],
  onViewMessages: MqWorkshopPipelineProps['onViewMessages'],
) {
  if (!q) return
  onViewMessages(q.name, mqQueueTitle(q.label, t), q.label, mainQueueDbSource(q.label))
}

export default function MqWorkshopPipeline({
  workshopKey,
  main,
  retry,
  dlq,
  health,
  activeTasks,
  display = 'inline',
  mode = 'admin',
  showExpand = false,
  onExpand,
  t,
  onViewMessages,
}: MqWorkshopPipelineProps) {
  const theme = useMqFactoryDesignTheme()
  const [themeState, setThemeState] = useState(theme)
  useEffect(() => {
    setThemeState(theme)
    const el = document.documentElement
    const obs = new MutationObserver(() => {
      setThemeState(el.getAttribute('data-theme') === 'dark' ? 'dark' : 'light')
    })
    obs.observe(el, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [theme])

  const labels = WORKSHOP_PIPELINE_LABELS[workshopKey]
  const taskKind = LABEL_TO_TASK_KIND[labels.main]
  const queueTasks = taskKind ? activeTasks.filter((task) => task.kind === taskKind) : []
  const isRunning = health === 'running' || !!main?.consumer_busy
  const backlog = main ? mqBacklogBreakdown(main) : { total: 0, queued: 0, running: 0 }
  const pkgCount = packageDisplayCount(main)
  const retryCount = retry?.message_count ?? 0
  const dlqCount = dlq?.message_count ?? 0
  const primaryTask = queueTasks[0]
  const layout = WORKSHOP_ROW_LAYOUT

  const rootClass = [
    'mq-design-row',
    `mq-design-row--${workshopKey}`,
    `mq-design-row--${display}`,
    isRunning ? 'mq-design-row--running' : '',
    health === 'attention' ? 'mq-design-row--attention' : '',
  ]
    .filter(Boolean)
    .join(' ')

  const showHealthOverlay = health !== 'idle' && !(workshopKey === 'post' && isRunning)

  return (
    <section
      className={rootClass}
      aria-label={t(TITLE_KEYS[workshopKey])}
      style={{ aspectRatio: `${layout.refWidth} / ${layout.refHeight}` }}
    >
      <img
        src={workshopRowImage(workshopKey, themeState)}
        alt=""
        className="mq-design-row__art"
        draggable={false}
      />

      {/* 左栏动态数字（覆盖设计图内 0） */}
      <span className="mq-design-overlay mq-design-overlay--metric" style={{ left: pct(layout.metrics.total.left), top: pct(layout.metrics.total.top) }}>
        {backlog.total}
      </span>
      <span className="mq-design-overlay mq-design-overlay--metric" style={{ left: pct(layout.metrics.queued.left), top: pct(layout.metrics.queued.top) }}>
        {backlog.queued}
      </span>
      <span className="mq-design-overlay mq-design-overlay--metric" style={{ left: pct(layout.metrics.running.left), top: pct(layout.metrics.running.top) }}>
        {backlog.running}
      </span>

      {/* 四站计数 */}
      <span className="mq-design-overlay mq-design-overlay--counter" style={{ left: pct(layout.counters.queue.left), top: pct(layout.counters.queue.top) }}>
        {pkgCount}
      </span>
      <span className="mq-design-overlay mq-design-overlay--counter" style={{ left: pct(layout.counters.process.left), top: pct(layout.counters.process.top) }}>
        {isRunning ? Math.max(backlog.running, 1) : backlog.running}
      </span>
      <span className="mq-design-overlay mq-design-overlay--counter mq-design-overlay--retry" style={{ left: pct(layout.counters.retry.left), top: pct(layout.counters.retry.top) }}>
        {retryCount}
      </span>
      <span className="mq-design-overlay mq-design-overlay--counter mq-design-overlay--dlq" style={{ left: pct(layout.counters.dlq.left), top: pct(layout.counters.dlq.top) }}>
        {dlqCount}
      </span>

      {showHealthOverlay ? (
        <span
          className={`mq-design-overlay mq-design-overlay--health mq-design-overlay--health-${health}`}
          style={{
            left: pct(layout.healthBadge.left),
            top: pct(layout.healthBadge.top),
            width: pct(layout.healthBadge.width),
          }}
        >
          {t(HEALTH_I18N[health])}
        </span>
      ) : null}

      {isRunning && primaryTask ? (
        <div
          className="mq-design-overlay mq-design-overlay--bubble"
          style={{
            left: pct(layout.bubble.left),
            top: pct(layout.bubble.minTop),
            width: pct(layout.bubble.width),
          }}
        >
          {mode === 'admin' && mqActiveTaskUsername(primaryTask) ? (
            <span className="mq-design-overlay__bubble-user">{mqActiveTaskUsername(primaryTask)}</span>
          ) : null}
          <span className="mq-design-overlay__bubble-file">
            <MqStorageFilenameCell filename={primaryTask.filename || `#${primaryTask.file_id ?? '?'}`} />
          </span>
        </div>
      ) : null}

      {showExpand && onExpand ? (
        <button type="button" className="mq-design-hit mq-design-hit--expand" style={{ left: pct(layout.hits.expand.left), top: pct(layout.hits.expand.top), width: pct(layout.hits.expand.width), height: pct(layout.hits.expand.height) }} onClick={onExpand} aria-label={t('admin.mq.factoryExpand')} />
      ) : null}

      <button type="button" className="mq-design-hit" style={{ left: pct(layout.hits.queue.left), top: pct(layout.hits.queue.top), width: pct(layout.hits.queue.width), height: pct(layout.hits.queue.height) }} onClick={() => openQueue(main, t, onViewMessages)} aria-label={t('admin.mq.factoryZoneQueue')} />
      <button type="button" className="mq-design-hit" style={{ left: pct(layout.hits.process.left), top: pct(layout.hits.process.top), width: pct(layout.hits.process.width), height: pct(layout.hits.process.height) }} onClick={() => openQueue(main, t, onViewMessages)} aria-label={t('admin.mq.factoryZoneProcess')} />
      <button type="button" className="mq-design-hit" style={{ left: pct(layout.hits.retry.left), top: pct(layout.hits.retry.top), width: pct(layout.hits.retry.width), height: pct(layout.hits.retry.height) }} onClick={() => openQueue(retry, t, onViewMessages)} aria-label={t('admin.mq.factoryZoneRetry')} />
      <button type="button" className="mq-design-hit" style={{ left: pct(layout.hits.dlq.left), top: pct(layout.hits.dlq.top), width: pct(layout.hits.dlq.width), height: pct(layout.hits.dlq.height) }} onClick={() => openQueue(dlq, t, onViewMessages)} aria-label={t('admin.mq.factoryZoneDlq')} />
    </section>
  )
}
