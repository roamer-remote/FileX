import { Drawer } from 'antd'
import { useEffect, useId, useState } from 'react'
import type { MqUserActiveTask } from '@/api/mq'
import type { MqQueueStatus, MqSystemResources } from '@/api/admin'
import { MqSidecarActiveTasks, type MainQueueDbSource } from '@/components/mq/MqQueueCard'
import {
  useMqFactoryQueuedJobs,
  type MqFactoryQueuedPreview,
} from '@/hooks/useMqFactoryQueuedJobs'
import MqFigmaSidecars from './figma/MqFigmaSidecars'
import MqFigmaSvgDefs from './figma/MqFigmaSvgDefs'
import MqFigmaWorkshopRow from './figma/MqFigmaWorkshopRow'
import {
  queueByLabelMap,
  workshopHealth,
  WORKSHOP_PIPELINE_LABELS,
  type WorkshopKey,
} from './mqFactoryMetrics'
import './MqFactoryFigma.css'

const DRAWER_TITLE_KEYS: Record<WorkshopKey, string> = {
  extract: 'admin.mq.groupExtract',
  index: 'admin.mq.groupIndex',
  post: 'admin.mq.groupPost',
}

const MAIN_WORKSHOPS: WorkshopKey[] = ['extract', 'index', 'post']

type MqFactoryViewProps = {
  sortedQueues: MqQueueStatus[]
  activeTasks: MqUserActiveTask[]
  systemResources?: MqSystemResources | null
  queuedPreviewsOverride?: Partial<Record<WorkshopKey, MqFactoryQueuedPreview>>
  mode?: 'admin' | 'user'
  showSidecarStations?: boolean
  t: (k: string, opts?: Record<string, unknown>) => string
  onViewMessages: (
    queueName: string,
    queueLabel: string,
    queueKey: string,
    dbSource: MainQueueDbSource,
  ) => void
}

export type MqResourceHistory = {
  cpu: number[]
  gpu: number[]
}

const RESOURCE_HISTORY_LIMIT = 18

function pushResourceValue(values: number[], value: number | null | undefined): number[] {
  if (value == null || !Number.isFinite(value)) return values
  return [...values, Math.max(0, Math.min(100, Math.round(value)))].slice(-RESOURCE_HISTORY_LIMIT)
}

export default function MqFactoryView({
  sortedQueues,
  activeTasks,
  systemResources,
  queuedPreviewsOverride,
  mode = 'admin',
  showSidecarStations = mode === 'admin',
  t,
  onViewMessages,
}: MqFactoryViewProps) {
  const [expandedWorkshop, setExpandedWorkshop] = useState<WorkshopKey | null>(null)
  const [resourceHistory, setResourceHistory] = useState<MqResourceHistory>({ cpu: [], gpu: [] })
  const queueMap = queueByLabelMap(sortedQueues)
  const reactId = useId()
  const idPrefix = `mqf${reactId.replace(/:/g, '')}`
  const fetchedPreviews = useMqFactoryQueuedJobs(sortedQueues, mode, !queuedPreviewsOverride)
  const queuedPreviews = queuedPreviewsOverride
    ? { ...fetchedPreviews, ...queuedPreviewsOverride }
    : fetchedPreviews

  useEffect(() => {
    if (!systemResources) return
    setResourceHistory((current) => ({
      cpu: pushResourceValue(current.cpu, systemResources.cpu_percent),
      gpu: systemResources.gpu.available
        ? pushResourceValue(current.gpu, systemResources.gpu.util_percent)
        : current.gpu,
    }))
  }, [systemResources])

  function renderPipeline(workshopKey: WorkshopKey, display: 'inline' | 'expanded', showExpand: boolean) {
    const labels = WORKSHOP_PIPELINE_LABELS[workshopKey]
    const main = queueMap.get(labels.main)
    const retry = queueMap.get(labels.retry)
    const dlq = queueMap.get(labels.dlq)
    const health = workshopHealth(main, retry, dlq)

    return (
      <MqFigmaWorkshopRow
        key={`${workshopKey}-${display}`}
        idPrefix={idPrefix}
        workshopKey={workshopKey}
        main={main}
        retry={retry}
        dlq={dlq}
        health={health}
        activeTasks={activeTasks}
        systemResources={systemResources}
        resourceHistory={resourceHistory}
        queuedPreview={queuedPreviews[workshopKey]}
        display={display}
        mode={mode}
        showExpand={showExpand}
        onExpand={showExpand ? () => setExpandedWorkshop(workshopKey) : undefined}
        t={t}
        onViewMessages={onViewMessages}
      />
    )
  }

  const expandedKey = expandedWorkshop

  return (
    <div className="mq-factory-view">
      <MqFigmaSvgDefs />
      <div className="mq-factory-view__pipelines">
        {MAIN_WORKSHOPS.map((key) => renderPipeline(key, 'inline', true))}
      </div>

      {showSidecarStations ? (
        <MqFigmaSidecars queues={sortedQueues} t={t} onViewMessages={onViewMessages} />
      ) : (
        <MqSidecarActiveTasks activeTasks={activeTasks} t={t} />
      )}

      <Drawer
        className="mq-factory-drawer"
        title={expandedKey ? t(DRAWER_TITLE_KEYS[expandedKey]) : ''}
        open={expandedKey != null}
        onClose={() => setExpandedWorkshop(null)}
        width="min(1496px, 96vw)"
        destroyOnClose={false}
      >
        {expandedKey ? renderPipeline(expandedKey, 'expanded', false) : null}
      </Drawer>
    </div>
  )
}
