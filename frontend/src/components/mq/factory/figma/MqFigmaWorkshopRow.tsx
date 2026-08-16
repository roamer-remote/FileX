import type { ReactNode } from 'react'
import { Progress } from 'antd'
import type { MqQueueStatus, MqSystemResources } from '@/api/admin'
import type { MqUserActiveTask } from '@/api/mq'
import { mqActiveTaskUsername } from '@/api/mq'
import {
  LABEL_TO_TASK_KIND,
  mainQueueDbSource,
  mqQueueTitle,
  type MainQueueDbSource,
} from '@/components/mq/MqQueueCard'
import type { MqFactoryQueuedPreview } from '@/hooks/useMqFactoryQueuedJobs'
import { mqBacklogBreakdown } from '@/utils/mqQueueMetrics'
import { storageFilenameDisplayName } from '@/utils/storageFilename'
import type { MqResourceHistory } from '../MqFactoryView'
import {
  packageDisplayCount,
  WORKSHOP_PIPELINE_LABELS,
  type WorkshopHealth,
  type WorkshopKey,
} from '../mqFactoryMetrics'
import {
  FIGMA_WORKSHOP_THEMES,
  HEALTH_LABEL,
  ILLUSTRATED_WORKSHOP_BACKGROUNDS,
  ILLUSTRATED_WORKSHOP_ROW,
} from './mqFigmaTheme'

export type MqWorkshopDisplay = 'inline' | 'expanded'

type MqFigmaWorkshopRowProps = {
  idPrefix: string
  workshopKey: WorkshopKey
  main?: MqQueueStatus
  retry?: MqQueueStatus
  dlq?: MqQueueStatus
  health: WorkshopHealth
  activeTasks: MqUserActiveTask[]
  systemResources?: MqSystemResources | null
  resourceHistory?: MqResourceHistory
  queuedPreview?: MqFactoryQueuedPreview
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

const RESOURCE_PANEL = {
  x: 30,
  y: 352,
  width: 390,
  height: 196,
} as const

const OVERLAY = {
  header: {
    badgePoints: '31,30 55,15 79,30 79,70 55,85 31,70',
    badgeText: { x: 55, y: 60 },
    titleText: { x: 126, y: 56 },
    healthText: { x: 342, y: 25, width: 102, height: 44 },
    routeLabel: { x: 31, y: 119 },
    routeText: { x: 146, y: 119 },
  },
  metrics: {
    total: { labelX: 74, x: 260, y: 184 },
    queued: { labelX: 74, x: 260, y: 231 },
    running: { labelX: 74, x: 260, y: 278 },
  },
  counters: {
    queue: { x: 482, y: 388, width: 152, height: 68 },
    process: { x: 919, y: 388, width: 154, height: 68 },
    retry: { x: 1338, y: 388, width: 154, height: 68 },
    dlq: { x: 1648, y: 388, width: 154, height: 68 },
  },
  taskBubble: { x: 858, y: 8, width: 390, height: 84 },
  queuePreview: { x: 446, y: 438, width: 330, height: 92 },
  hits: {
    queue: { x: 410, y: 149, width: 290, height: 282 },
    process: { x: 800, y: 70, width: 420, height: 360 },
    retry: { x: 1270, y: 164, width: 282, height: 260 },
    dlq: { x: 1600, y: 179, width: 230, height: 255 },
    expand: { x: 1865, y: 129, width: 230, height: 320 },
  },
} as const

function openQueue(
  q: MqQueueStatus | undefined,
  t: MqFigmaWorkshopRowProps['t'],
  onViewMessages: MqFigmaWorkshopRowProps['onViewMessages'],
) {
  if (!q) return
  onViewMessages(q.name, mqQueueTitle(q.label, t), q.label, mainQueueDbSource(q.label))
}

function taskProgressPercent(task: MqUserActiveTask): number | undefined {
  if (task.progress_pct == null || !Number.isFinite(task.progress_pct)) {
    return undefined
  }
  return Math.max(0, Math.min(100, Math.round(task.progress_pct)))
}

function hasTaskProgress(task: MqUserActiveTask): boolean {
  return Boolean(task.progress_stage && task.progress_stage.trim().length > 0)
}

function taskBubbleFilename(task: MqUserActiveTask): string {
  const raw = task.filename?.trim() || `#${task.file_id ?? '?'}`
  return storageFilenameDisplayName(raw)
}

function pctText(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${Math.round(Math.max(0, Math.min(100, value)))}%`
}

function percentBar(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '0%'
  return `${Math.max(0, Math.min(100, value))}%`
}

function memoryText(usedMb: number | null | undefined, totalMb: number | null | undefined): string {
  if (usedMb == null || totalMb == null || totalMb <= 0) return '—'
  return `${(usedMb / 1024).toFixed(1)} / ${(totalMb / 1024).toFixed(1)}GB`
}

function memoryPercent(resources: MqSystemResources): number | null {
  const used = resources.gpu.memory_used_mb
  const total = resources.gpu.memory_total_mb
  if (used == null || total == null || total <= 0) return null
  return Math.max(0, Math.min(100, (used / total) * 100))
}

function capabilityLabel(capability: MqSystemResources['gpu']['capability'], t: MqFigmaWorkshopRowProps['t']): string | undefined {
  if (!capability) return undefined
  const key = {
    high: 'admin.mq.factoryResourceCapabilityHigh',
    medium: 'admin.mq.factoryResourceCapabilityMedium',
    low: 'admin.mq.factoryResourceCapabilityLow',
    cpu_only: 'admin.mq.factoryResourceCapabilityCpuOnly',
  }[capability]
  return t(key)
}

function reasonLabel(reasonCode: MqSystemResources['gpu']['reason_code'], t: MqFigmaWorkshopRowProps['t']): string | undefined {
  if (!reasonCode) return undefined
  const key = {
    cpu_only_no_cuda: 'admin.mq.factoryResourceReasonNoCuda',
    cpu_only_probe_failed: 'admin.mq.factoryResourceReasonProbeFailed',
    cpu_only_insufficient_memory: 'admin.mq.factoryResourceReasonInsufficientMemory',
  }[reasonCode]
  return t(key)
}

function modelGroupLabel(
  modelGroup: string | null | undefined,
  t: MqFigmaWorkshopRowProps['t'],
): string | undefined {
  if (!modelGroup) return undefined
  const key = {
    none: 'admin.mq.factoryModelGroupNone',
    raptor: 'admin.mq.factoryModelGroupRaptor',
    mineru: 'admin.mq.factoryModelGroupMineru',
    switching: 'admin.mq.factoryModelGroupSwitching',
  } as Record<string, string>
  return key[modelGroup] ? t(key[modelGroup]) : modelGroup
}

function switchDurationText(
  ms: number | null | undefined,
  t: MqFigmaWorkshopRowProps['t'],
): string | undefined {
  if (ms == null || !Number.isFinite(ms)) return undefined
  const seconds = ms >= 1000 ? (ms / 1000).toFixed(1) : String(ms)
  return t('admin.mq.factoryLastSwitch', { seconds })
}

function sparklinePoints(values: number[], width = 42, height = 14): string {
  const series = values.length >= 2 ? values : [0, ...(values.length === 1 ? values : [0])]
  const maxIndex = Math.max(1, series.length - 1)
  return series
    .map((value, index) => {
      const x = (index / maxIndex) * width
      const y = height - (Math.max(0, Math.min(100, value)) / 100) * height
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

function ResourceLine({
  label,
  value,
  barValue,
  history,
  tone = 'blue',
  tag,
}: {
  label: string
  value: string
  barValue: number | null | undefined
  history?: number[]
  tone?: 'blue' | 'green' | 'cyan' | 'amber'
  tag?: string
}) {
  return (
    <div
      className={`mq-figma-resource-row mq-figma-resource-row--${tone}`}
    >
      <span className="mq-figma-resource-row__label">{label}</span>
      <span className="mq-figma-resource-row__value">{value}</span>
      <span className="mq-figma-resource-row__bar" aria-hidden>
        <span style={{ width: percentBar(barValue) }} />
      </span>
      {history || tag ? (
        <span className="mq-figma-resource-row__trailing">
          {history ? (
            <svg className="mq-figma-resource-row__spark" viewBox="0 0 42 14" aria-hidden>
              <polyline points={sparklinePoints(history)} />
            </svg>
          ) : null}
          {tag ? <span className="mq-figma-resource-row__tag">{tag}</span> : null}
        </span>
      ) : null}
    </div>
  )
}

function SystemResourcePanel({
  resources,
  history,
  workshopKey,
  activeStage,
  activeModel,
  t,
}: {
  resources: MqSystemResources
  history?: MqResourceHistory
  workshopKey: WorkshopKey
  activeStage?: string | null
  activeModel?: string | null
  t: MqFigmaWorkshopRowProps['t']
}) {
  const gpu = resources.gpu
  const scheduler = resources.gpu_scheduler
  const waiting = resources.gpu_waiting
  const capability = gpu.capability ?? (gpu.available ? undefined : 'cpu_only')
  const gpuUsable = gpu.gpu_usable ?? (gpu.available && capability !== 'cpu_only')
  const capabilityText = capabilityLabel(capability, t)
  const reasonText = reasonLabel(gpu.reason_code, t)
  const lastSwitchText = switchDurationText(scheduler?.last_switch_duration_ms, t)
  const schedulerTitle = scheduler?.last_failure_reason
    ? t('admin.mq.factoryLastFailure', { reason: scheduler.last_failure_reason })
    : undefined
  const waitingTitle = waiting?.reason_codes?.length ? waiting.reason_codes.join(', ') : undefined
  const gpuTone = gpu.util_percent != null && gpu.util_percent >= 80 ? 'amber' : workshopKey === 'index' ? 'green' : workshopKey === 'post' ? 'cyan' : 'blue'
  const rowTone = workshopKey === 'index' ? 'green' : workshopKey === 'post' ? 'cyan' : 'blue'
  const workflowKey = {
    extract: 'admin.mq.groupExtract',
    index: 'admin.mq.groupIndex',
    post: 'admin.mq.groupPost',
  }[workshopKey]
  const processingStage = activeStage?.trim() || modelGroupLabel(scheduler?.model_group, t) || t(workflowKey)
  const processingModel = activeModel?.trim() || '—'
  return (
    <foreignObject
      x={RESOURCE_PANEL.x}
      y={RESOURCE_PANEL.y}
      width={RESOURCE_PANEL.width}
      height={RESOURCE_PANEL.height}
    >
      <div className={`mq-figma-resource-panel mq-figma-resource-panel--${workshopKey}`}>
        <div className="mq-figma-resource-panel__head">
          <span>{t('admin.mq.factoryResourceTitle')}</span>
          {gpuUsable ? (
            <span className="mq-figma-resource-panel__status" title={reasonText}>
              {t('admin.mq.factoryResourceRunning')}
              {capabilityText ? ` · ${capabilityText}` : ''}
            </span>
          ) : null}
        </div>
        <ResourceLine
          label={t('admin.mq.factoryResourceCpu')}
          value={pctText(resources.cpu_percent)}
          barValue={resources.cpu_percent}
          history={history?.cpu}
          tone={rowTone}
        />
        {gpu.available ? (
          <>
            <ResourceLine
              label={t('admin.mq.factoryResourceGpu')}
              value={pctText(gpu.util_percent)}
              barValue={gpu.util_percent}
              history={history?.gpu}
              tone={gpuTone}
              tag={gpu.name ? 'NVIDIA' : undefined}
            />
            <ResourceLine
              label={t('admin.mq.factoryResourceVram')}
              value={memoryText(gpu.memory_used_mb, gpu.memory_total_mb)}
              barValue={memoryPercent(resources)}
              tone={rowTone}
            />
          </>
        ) : null}
        {scheduler ? (
          <div className="mq-figma-resource-panel__meta" title={schedulerTitle}>
            <span className="mq-figma-resource-panel__meta-label">
              {t('admin.mq.factoryResourceModelGroup')}
            </span>
            <span className="mq-figma-resource-panel__meta-value">
              {modelGroupLabel(scheduler.model_group, t) ?? '—'}
              {lastSwitchText ? ` · ${lastSwitchText}` : ''}
            </span>
          </div>
        ) : null}
        <div className="mq-figma-resource-panel__meta">
          <span className="mq-figma-resource-panel__meta-label">
            {t('admin.mq.factoryResourceProcessing')}
          </span>
          <span className="mq-figma-resource-panel__meta-value" title={processingModel}>
            {processingStage} · {processingModel}
          </span>
        </div>
        {waiting && waiting.count > 0 ? (
          <div
            className="mq-figma-resource-panel__meta mq-figma-resource-panel__meta--waiting"
            title={waitingTitle}
          >
            <span className="mq-figma-resource-panel__meta-value">
              {t('admin.mq.factoryWaitingGpu', {
                count: waiting.count,
                seconds: waiting.oldest_wait_seconds ?? '—',
              })}
            </span>
          </div>
        ) : null}
      </div>
    </foreignObject>
  )
}

type QueuePanelRow = {
  key: string
  filename: string
  username?: string
}

/** DB queued jobs + serial 消费时其余 active_tasks（同为 running 但未在加工台展示） */
function buildQueuePanelRows(
  queuedPreview: MqFactoryQueuedPreview | undefined,
  waitingActive: MqUserActiveTask[],
  mode: 'admin' | 'user',
): { rows: QueuePanelRow[]; total: number } {
  const apiItems = queuedPreview?.items ?? []
  const apiFileIds = new Set(apiItems.map((item) => item.file_id))
  const rows: QueuePanelRow[] = apiItems.map((item) => ({
    key: `job-${item.job_id}`,
    filename: item.filename,
    username: mode === 'admin' ? item.username : undefined,
  }))
  let extraWaiting = 0
  for (const task of waitingActive) {
    const fileId = task.file_id
    if (fileId == null || apiFileIds.has(fileId)) continue
    extraWaiting += 1
    rows.push({
      key: `active-${fileId}`,
      filename: taskBubbleFilename(task),
      username: mode === 'admin' ? mqActiveTaskUsername(task) ?? undefined : undefined,
    })
  }
  return { rows, total: (queuedPreview?.total ?? 0) + extraWaiting }
}

export default function MqFigmaWorkshopRow({
  workshopKey,
  main,
  retry,
  dlq,
  health,
  activeTasks,
  systemResources,
  resourceHistory,
  queuedPreview,
  display = 'inline',
  mode = 'admin',
  showExpand,
  onExpand,
  t,
  onViewMessages,
}: MqFigmaWorkshopRowProps) {
  const theme = FIGMA_WORKSHOP_THEMES[workshopKey]
  const rowLayout = ILLUSTRATED_WORKSHOP_ROW
  const backgroundHref = ILLUSTRATED_WORKSHOP_BACKGROUNDS[workshopKey]
  const labels = WORKSHOP_PIPELINE_LABELS[workshopKey]
  const taskKind = LABEL_TO_TASK_KIND[labels.main]
  const queueTasks = taskKind ? activeTasks.filter((task) => task.kind === taskKind) : []
  const primary = queueTasks[0]

  const isRunning = health === 'running' || !!main?.consumer_busy
  const backlog = main ? mqBacklogBreakdown(main) : { total: 0, queued: 0, running: 0 }
  const pkgCount = packageDisplayCount(main)
  const retryCount = retry?.message_count ?? 0
  const dlqCount = dlq?.message_count ?? 0
  const processCount = isRunning ? Math.max(backlog.running, 1) : backlog.running

  const titleText = `${t(theme.titleKey)}${t('admin.mq.factoryWorkshopSuffix')}`
  const healthLabel = t(HEALTH_LABEL[health])
  const robotStatusZh = isRunning ? t('admin.mq.factoryHealthRunning') : t('admin.mq.factoryRobotIdle')

  let taskBubble: ReactNode = null
  if (isRunning && primary) {
    const pct = taskProgressPercent(primary)
    const showProgress = hasTaskProgress(primary)
    taskBubble = (
      <foreignObject
        x={OVERLAY.taskBubble.x}
        y={OVERLAY.taskBubble.y}
        width={OVERLAY.taskBubble.width}
        height={OVERLAY.taskBubble.height}
        pointerEvents="none"
      >
        <div className="mq-figma-task-bubble mq-figma-task-bubble--callout">
          {mode === 'admin' && mqActiveTaskUsername(primary) ? (
            <span className="mq-figma-task-bubble__user">{mqActiveTaskUsername(primary)}</span>
          ) : null}
          <span className="mq-figma-task-bubble__file" title={taskBubbleFilename(primary)}>
            {taskBubbleFilename(primary)}
          </span>
          {showProgress ? (
            <div className="mq-figma-task-bubble__progress">
              <div className="mq-figma-task-bubble__stage">
                {primary.progress_stage}
                {primary.progress_detail ? (
                  <span className="mq-figma-task-bubble__detail"> · {primary.progress_detail}</span>
                ) : null}
              </div>
              <Progress
                percent={pct}
                size="small"
                showInfo={pct != null}
                status={pct == null ? 'active' : undefined}
                strokeColor="var(--mq-figma-progress-stroke)"
              />
            </div>
          ) : null}
        </div>
      </foreignObject>
    )
  }

  const waitingActive = queueTasks.slice(1)
  const { rows: queuePanelRows, total: queuePanelTotal } = buildQueuePanelRows(
    queuedPreview,
    waitingActive,
    mode,
  )
  const queuePanelDisplay = queuePanelRows.slice(0, 3)
  let queuePreviewPanel: ReactNode = null
  if (queuePanelRows.length > 0) {
    queuePreviewPanel = (
      <foreignObject
        x={OVERLAY.queuePreview.x}
        y={OVERLAY.queuePreview.y}
        width={OVERLAY.queuePreview.width}
        height={OVERLAY.queuePreview.height}
      >
        <div className="mq-figma-queue-preview">
          <div className="mq-figma-queue-preview__title">{t('admin.mq.factoryQueuePreviewTitle')}</div>
          <ul className="mq-figma-queue-preview__list">
            {queuePanelDisplay.map((item) => (
              <li key={item.key} className="mq-figma-queue-preview__item">
                <span className="mq-figma-queue-preview__wait">{t('admin.mq.factoryQueueItemWaiting')}</span>
                {mode === 'admin' && item.username ? (
                  <span className="mq-figma-queue-preview__user">{item.username}</span>
                ) : null}
                <span className="mq-figma-queue-preview__file" title={storageFilenameDisplayName(item.filename)}>
                  {storageFilenameDisplayName(item.filename)}
                </span>
              </li>
            ))}
          </ul>
          {queuePanelTotal > 3 ? (
            <button
              type="button"
              className="mq-figma-queue-preview__more mq-figma-hit"
              onClick={() => openQueue(main, t, onViewMessages)}
            >
              {t('admin.mq.factoryViewAllQueued', { count: queuePanelTotal })}
            </button>
          ) : null}
        </div>
      </foreignObject>
    )
  }

  return (
    <div
      className={`mq-figma-row mq-figma-row--${workshopKey} mq-figma-row--${display}${isRunning ? ' mq-figma-row--running' : ''}`}
    >
      <svg
        width={rowLayout.width}
        height={rowLayout.height}
        viewBox={`0 0 ${rowLayout.width} ${rowLayout.height}`}
        className="mq-figma-row__svg"
        role="img"
        aria-label={titleText}
      >
        <image
          href={backgroundHref}
          width={rowLayout.width}
          height={rowLayout.height}
          preserveAspectRatio="xMidYMid meet"
          className="mq-figma-row__background"
        />

        <g className="mq-figma-bitmap-hud">
          <polygon points={OVERLAY.header.badgePoints} fill={theme.hexFill} stroke={theme.hexStroke} strokeWidth="3" />
          <text
            x={OVERLAY.header.badgeText.x}
            y={OVERLAY.header.badgeText.y}
            textAnchor="middle"
            className="mq-figma-bitmap-hud__badge"
          >
            {theme.workshopIndex}
          </text>
          <text x={OVERLAY.header.titleText.x} y={OVERLAY.header.titleText.y} className="mq-figma-bitmap-hud__title">
            {titleText}
          </text>
          <foreignObject
            x={OVERLAY.header.healthText.x}
            y={OVERLAY.header.healthText.y}
            width={OVERLAY.header.healthText.width}
            height={OVERLAY.header.healthText.height}
            className="mq-figma-bitmap-hud__health-slot"
            pointerEvents="none"
          >
            <div className="mq-figma-bitmap-hud__health" style={{ color: theme.healthTextFill }}>
              {healthLabel}
            </div>
          </foreignObject>
          <text x={OVERLAY.header.routeLabel.x} y={OVERLAY.header.routeLabel.y} className="mq-figma-bitmap-hud__label">
            路由键
          </text>
          <text x={OVERLAY.header.routeText.x} y={OVERLAY.header.routeText.y} className="mq-figma-bitmap-hud__route" fill={theme.routeTextFill}>
            {theme.routeKey}
          </text>

          {(Object.entries(OVERLAY.metrics) as [keyof typeof OVERLAY.metrics, (typeof OVERLAY.metrics)['total']][]).map(([key, box]) => {
            const value = key === 'total' ? backlog.total : key === 'queued' ? backlog.queued : backlog.running
            const labelKey = key === 'total' ? 'admin.mq.backlogTotal' : key === 'queued' ? 'admin.mq.backlogQueued' : 'admin.mq.backlogRunning'
            const hotClass = key === 'total' && isRunning && backlog.total > 0
              ? ' mq-figma-bitmap-hud__metric--hot'
              : key === 'running' && isRunning && backlog.running > 0
                ? ' mq-figma-bitmap-hud__metric--running'
                : ''
            return (
              <g key={key}>
                <text x={box.labelX} y={box.y + 8} className="mq-figma-bitmap-hud__label">
                  {t(labelKey)}
                </text>
                <text x={box.x} y={box.y} className={`mq-figma-bitmap-hud__metric${hotClass}`}>
                  {value}
                </text>
              </g>
            )
          })}

          <g className={isRunning ? 'mq-figma-bitmap-flow mq-figma-bitmap-flow--running' : 'mq-figma-bitmap-flow'} aria-hidden>
            <path d="M635 318 H837 M1205 318 H1310 M1538 318 H1630" />
          </g>

          {isRunning ? taskBubble : null}
          {queuePreviewPanel}

          {(Object.entries(OVERLAY.counters) as [keyof typeof OVERLAY.counters, (typeof OVERLAY.counters)['queue']][]).map(([key, box]) => {
            const value = key === 'queue' ? pkgCount : key === 'process' ? processCount : key === 'retry' ? retryCount : dlqCount
            const prefix = key === 'process' ? '▶' : '◆'
            const isHot = (key === 'retry' && retryCount > 0) || (key === 'dlq' && dlqCount > 0)
            return (
              <foreignObject
                key={key}
                x={box.x}
                y={box.y}
                width={box.width}
                height={box.height}
                className={`mq-figma-bitmap-counter-slot mq-figma-bitmap-counter--${key}${isHot ? ' mq-figma-bitmap-counter--hot' : ''}`}
                pointerEvents="none"
              >
                <div className="mq-figma-bitmap-counter__value">
                  <span className="mq-figma-bitmap-counter__icon">{prefix}</span>
                  <span>{value}</span>
                </div>
              </foreignObject>
            )
          })}

          <text
            x="2050"
            y="238"
            textAnchor="middle"
            dominantBaseline="middle"
            className="mq-figma-bitmap-hud__robot-status"
            fill={theme.robotStatusColor}
          >
            {robotStatusZh}
          </text>
        </g>

        {isRunning && systemResources ? (
          <SystemResourcePanel
            resources={systemResources}
            history={resourceHistory}
            workshopKey={workshopKey}
            activeStage={primary?.progress_stage}
            activeModel={primary?.model}
            t={t}
          />
        ) : null}

        <rect {...OVERLAY.hits.queue} fill="transparent" className="mq-figma-hit" onClick={() => openQueue(main, t, onViewMessages)} />
        <rect {...OVERLAY.hits.process} fill="transparent" className="mq-figma-hit" onClick={() => openQueue(main, t, onViewMessages)} />
        <rect {...OVERLAY.hits.retry} fill="transparent" className="mq-figma-hit" onClick={() => openQueue(retry, t, onViewMessages)} />
        <rect {...OVERLAY.hits.dlq} fill="transparent" className="mq-figma-hit" onClick={() => openQueue(dlq, t, onViewMessages)} />
        {showExpand && onExpand ? (
          <rect
            {...OVERLAY.hits.expand}
            fill="transparent"
            className="mq-figma-hit"
            onClick={onExpand}
            role="button"
            tabIndex={0}
            aria-label={`${t('admin.mq.factoryRobotStatus')}，${t('admin.mq.factoryExpand')}`}
          />
        ) : null}
      </svg>
    </div>
  )
}
