import { useEffect, useState } from 'react'
import type { MqQueueStatus } from '@/api/admin'
import { mqQueueTitle, type MainQueueDbSource } from '@/components/mq/MqQueueCard'
import { mqBacklogBreakdown } from '@/utils/mqQueueMetrics'
import { SIDECAR_LABELS } from './mqFactoryMetrics'
import { SIDECAR_LAYOUT, sidecarsImage, useMqFactoryDesignTheme } from './mqFactoryDesignLayout'

type MqSidecarStationsProps = {
  queues: MqQueueStatus[]
  t: (k: string, opts?: Record<string, unknown>) => string
  onViewMessages: (
    queueName: string,
    queueLabel: string,
    queueKey: string,
    dbSource: MainQueueDbSource,
  ) => void
}

function pct(v: number) {
  return `${v}%`
}

export default function MqSidecarStations({ queues, t, onViewMessages }: MqSidecarStationsProps) {
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

  const byLabel = new Map(queues.map((q) => [q.label, q]))
  const items = SIDECAR_LABELS.map((label) => byLabel.get(label)).filter((q): q is MqQueueStatus => !!q)
  if (items.length === 0) return null

  const layout = SIDECAR_LAYOUT

  return (
    <section
      className="mq-design-sidecars"
      aria-label={t('admin.mq.factorySidecarTitle')}
      style={{ aspectRatio: `${layout.refWidth} / ${layout.refHeight}` }}
    >
      <img src={sidecarsImage(themeState)} alt="" className="mq-design-sidecars__art" draggable={false} />

      {items.map((q, i) => {
        const card = layout.cards[i]
        const hit = layout.hits[i]
        const breakdown = mqBacklogBreakdown(q)
        if (!card || !hit) return null
        return (
          <div key={q.name}>
            <span
              className="mq-design-overlay mq-design-overlay--sidecar-metric"
              style={{ left: pct(card.left + 4), top: pct(card.metricsTop), width: pct(card.width - 8) }}
            >
              <span>{breakdown.total}</span>
              <span>{breakdown.queued}</span>
              <span>{breakdown.running}</span>
            </span>
            <button
              type="button"
              className="mq-design-hit"
              style={{
                left: pct(hit.left),
                top: pct(hit.top),
                width: pct(hit.width),
                height: pct(hit.height),
              }}
              onClick={() => onViewMessages(q.name, mqQueueTitle(q.label, t), q.label, null)}
              aria-label={mqQueueTitle(q.label, t)}
            />
          </div>
        )
      })}
    </section>
  )
}
