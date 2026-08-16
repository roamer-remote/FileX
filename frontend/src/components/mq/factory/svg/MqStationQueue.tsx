import MqGlassCube from './MqGlassCube'
import MqStationCounter from './MqStationCounter'
import { isoPedestalPaths } from './mqIsometry'

type MqStationQueueProps = {
  label: string
  count: number
  extra: number
  emptyLabel?: string
  idPrefix?: string
}

function QueueSheet({ index, total }: { index: number; total: number }) {
  const depth = total - 1 - index
  const cx = 60 - depth * 2.5
  const top = 46 + depth * 2.5
  return (
    <g className="mq-factory-station-queue__sheet" style={{ ['--sheet-i' as string]: index }}>
      <path
        d={`M${cx - 12} ${top + 5} L${cx} ${top} L${cx + 12} ${top + 5} L${cx} ${top + 10} Z`}
        className="mq-factory-station-queue__sheet-top"
      />
      <path
        d={`M${cx - 12} ${top + 5} L${cx - 12} ${top + 13} L${cx} ${top + 18} L${cx} ${top + 10} Z`}
        className="mq-factory-station-queue__sheet-left"
      />
      <path
        d={`M${cx} ${top + 10} L${cx} ${top + 18} L${cx + 12} ${top + 13} L${cx + 12} ${top + 5} Z`}
        className="mq-factory-station-queue__sheet-right"
      />
    </g>
  )
}

export default function MqStationQueue({
  label,
  count,
  extra,
  emptyLabel,
  idPrefix = 'mqQueue',
}: MqStationQueueProps) {
  const total = count + extra
  const visibleSheets = Math.min(count, 5)
  const hasItems = total > 0
  const pedestal = isoPedestalPaths(60, 72, 52, 14)

  return (
    <div className={`mq-factory-station-graphic mq-factory-station-queue${hasItems ? ' mq-factory-station-queue--filled' : ''}`}>
      <svg className="mq-factory-station-graphic__svg" viewBox="0 0 120 108" aria-hidden>
        <ellipse cx="60" cy="82" rx="26" ry="5" className="mq-factory-station-graphic__shadow" />
        <g className="mq-factory-station-graphic__pedestal">
          <path d={pedestal.top} className="mq-factory-station-graphic__pedestal-top" />
          <path d={pedestal.left} className="mq-factory-station-graphic__pedestal-left" />
          <path d={pedestal.right} className="mq-factory-station-graphic__pedestal-right" />
        </g>
        <MqGlassCube idPrefix={`${idPrefix}-cube`} cx={60} cy={50} size={18} glow={hasItems}>
          {visibleSheets > 0 ? (
            Array.from({ length: visibleSheets }, (_, i) => (
              <QueueSheet key={i} index={i} total={visibleSheets} />
            ))
          ) : (
            <g className="mq-factory-station-queue__stack-icon">
              <path d="M48 48 L72 48 L72 52 L48 52 Z" className="mq-factory-station-queue__empty-bar" />
              <path d="M50 54 L70 54 L70 58 L50 58 Z" className="mq-factory-station-queue__empty-bar" />
              <path d="M52 60 L68 60 L68 64 L52 64 Z" className="mq-factory-station-queue__empty-bar mq-factory-station-queue__empty-bar--dim" />
            </g>
          )}
        </MqGlassCube>
        <MqStationCounter value={hasItems ? total : 0} icon="arrow" />
      </svg>
      <span className="mq-factory-station-graphic__label">{label}</span>
      {!hasItems && emptyLabel ? (
        <span className="mq-factory-packages__empty">{emptyLabel}</span>
      ) : null}
    </div>
  )
}
