import type { ReactNode } from 'react'
import type { MqQueueStatus } from '@/api/admin'
import { mqQueueTitle, type MainQueueDbSource } from '@/components/mq/MqQueueCard'
import { mqBacklogBreakdown } from '@/utils/mqQueueMetrics'
import { SIDECAR_LABELS, sidecarMetricsDisplay, type WorkshopHealth } from '../mqFactoryMetrics'
import {
  FigmaBranchBellIcon,
  FigmaBranchCardShell,
  FigmaBranchDocIcon,
  FigmaBranchPdfIcon,
} from './mqFigmaConcreteParts'
import {
  FIGMA_BRANCH_LAYOUT,
  FIGMA_BRANCH_METRICS,
  FIGMA_SIDECAR,
  HEALTH_LABEL,
  figmaBranchMetricX,
  figmaSidecarCardWidth,
  figmaSidecarCardX,
  figmaSidecarTagX,
  type FigmaBranchCardKey,
} from './mqFigmaTheme'

type MqFigmaSidecarsProps = {
  queues: MqQueueStatus[]
  t: (k: string, opts?: Record<string, unknown>) => string
  onViewMessages: (
    queueName: string,
    queueLabel: string,
    queueKey: string,
    dbSource: MainQueueDbSource,
  ) => void
}

function sidecarHealth(q: MqQueueStatus): WorkshopHealth {
  if (!q.online) return 'attention'
  if (q.consumer_busy) return 'running'
  const backlog = mqBacklogBreakdown(q)
  if (backlog.total > 0 || (q.message_count ?? 0) > 0) return 'backlog'
  return 'idle'
}

function branchCardIcon(card: FigmaBranchCardKey): ReactNode {
  switch (card) {
    case 'branchCardBlue':
      return <FigmaBranchBellIcon tone="blue" />
    case 'branchCardGreen':
      return <FigmaBranchBellIcon tone="green" />
    case 'branchCardPurple':
      return <FigmaBranchPdfIcon tone="purple" />
    case 'branchCardOrange':
      return <FigmaBranchDocIcon tone="orange" />
    default: {
      const _exhaustive: never = card
      return _exhaustive
    }
  }
}

export default function MqFigmaSidecars({ queues, t, onViewMessages }: MqFigmaSidecarsProps) {
  const byLabel = new Map(queues.map((q) => [q.label, q]))
  const items = SIDECAR_LABELS.map((label) => byLabel.get(label)).filter((q): q is MqQueueStatus => !!q)
  if (items.length === 0) return null

  const sectionTitle = t('admin.mq.factorySidecarTitle')
  const { viewWidth, viewHeight, headerOffsetY, branchRowY, cardHeight } = FIGMA_SIDECAR
  const cardWidth = figmaSidecarCardWidth()
  const tagX = figmaSidecarTagX(cardWidth)

  return (
    <section className="mq-figma-sidecars" aria-label={sectionTitle}>
      <svg
        viewBox={`0 0 ${viewWidth} ${viewHeight}`}
        className="mq-figma-sidecars__svg"
        role="img"
        aria-label={sectionTitle}
      >
        <rect width={viewWidth} height={viewHeight} rx="9" className="mq-figma-panel mq-figma-shadow" />

        <g transform={`translate(21 ${headerOffsetY})`}>
          <path d="M17 0 L32 9 L32 29 L17 39 L2 29 L2 9Z" fill="#7367e8" stroke="#d5d0ff" strokeWidth="3" />
          <text x="11" y="27" fill="#fff" fontSize="25" fontWeight="700" fontFamily="sans-serif">
            4
          </text>
          <text x="76" y="24" className="mq-figma-h2">
            {sectionTitle}
          </text>
        </g>

        {FIGMA_BRANCH_LAYOUT.map((branch, index) => {
          const q = items[index]
          if (!q) return null
          const health = sidecarHealth(q)
          const healthLabel = t(HEALTH_LABEL[health])
          const isRunning = health === 'running'
          const tagClass = isRunning && branch.runningTagClass ? branch.runningTagClass : branch.tagClass
          const tagFill = isRunning && branch.runningTextFill ? branch.runningTextFill : branch.healthTextFill
          const title = mqQueueTitle(branch.label, t)
          const cardX = figmaSidecarCardX(index)
          const metrics = sidecarMetricsDisplay(q)
          const metricValues = [metrics.total, metrics.queued, metrics.running]

          return (
            <g
              key={branch.label}
              className={isRunning ? 'mq-figma-branch mq-figma-branch--running' : 'mq-figma-branch'}
              transform={`translate(${cardX} ${branchRowY})`}
            >
              <FigmaBranchCardShell width={cardWidth} height={cardHeight} />
              <g transform="translate(20 15)">{branchCardIcon(branch.card)}</g>
              <text x="126" y="42" className="mq-figma-h2">
                {title}
              </text>
              <text x="126" y="68" className="mq-figma-body">
                {branch.label}
              </text>
              <rect x={tagX} y="51" width="66" height="27" rx="6" className={tagClass} />
              <text x={tagX + 15} y="70" fontSize="13" fontWeight="700" fill={tagFill} fontFamily="sans-serif">
                {healthLabel}
              </text>
              {FIGMA_BRANCH_METRICS.columns.map((col, metricIndex) => (
                <text
                  key={col.i18nKey}
                  x={figmaBranchMetricX(cardWidth, col.designX)}
                  y={FIGMA_BRANCH_METRICS.rowY}
                  className="mq-figma-body mq-figma-branch-metric"
                >
                  {'separator' in col ? col.separator : ''}
                  {t(col.i18nKey)} {metricValues[metricIndex]}
                </text>
              ))}
              {isRunning ? (
                <rect
                  x="0"
                  y="0"
                  width={cardWidth}
                  height={cardHeight}
                  rx="12"
                  fill="none"
                  stroke="#22d3ee"
                  strokeWidth="2"
                  className="mq-figma-branch-glow-live"
                />
              ) : null}
              <rect
                x="0"
                y="0"
                width={cardWidth}
                height={cardHeight}
                fill="transparent"
                className="mq-figma-hit"
                onClick={() => onViewMessages(q.name, title, q.label ?? branch.label, null)}
              />
            </g>
          )
        })}
      </svg>
    </section>
  )
}
