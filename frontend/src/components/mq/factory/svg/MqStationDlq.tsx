import MqGlassCube from './MqGlassCube'
import MqStationCounter from './MqStationCounter'
import { isoPedestalPaths } from './mqIsometry'

type MqStationDlqProps = {
  label: string
  count: number
  idPrefix?: string
}

export default function MqStationDlq({ label, count, idPrefix = 'mqDlq' }: MqStationDlqProps) {
  const pedestal = isoPedestalPaths(60, 72, 48, 14)
  const alert = count > 0

  return (
    <div className={`mq-factory-station-graphic mq-factory-station-dlq${alert ? ' mq-factory-station-dlq--alert' : ''}`}>
      <svg className="mq-factory-station-graphic__svg" viewBox="0 0 120 108" aria-hidden>
        <ellipse cx="60" cy="82" rx="26" ry="5" className="mq-factory-station-graphic__shadow" />
        <g className="mq-factory-station-graphic__pedestal">
          <path d={pedestal.top} className="mq-factory-station-graphic__pedestal-top" />
          <path d={pedestal.left} className="mq-factory-station-graphic__pedestal-left" />
          <path d={pedestal.right} className="mq-factory-station-graphic__pedestal-right" />
        </g>
        <MqGlassCube idPrefix={`${idPrefix}-cube`} cx={60} cy={50} size={18} glow={alert}>
          <g className="mq-factory-station-dlq__icon">
            <path d="M52 58 L68 58 L68 62 L52 62 Z" className="mq-factory-station-dlq__bin-top" />
            <path d="M54 62 L66 62 L64 72 L56 72 Z" className="mq-factory-station-dlq__bin-body" />
            <path d="M56 66 L58 70 M60 66 L60 70 M64 66 L62 70" className="mq-factory-station-dlq__recycle" fill="none" strokeWidth="1.5" strokeLinecap="round" />
          </g>
        </MqGlassCube>
        <MqStationCounter value={count} icon="recycle" alert={alert} />
      </svg>
      <span className="mq-factory-station-graphic__label">{label}</span>
    </div>
  )
}
