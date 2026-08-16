import MqGlassCube from './MqGlassCube'
import MqStationCounter from './MqStationCounter'
import { isoPedestalPaths } from './mqIsometry'

type MqStationRetryProps = {
  label: string
  count: number
  idPrefix?: string
}

export default function MqStationRetry({ label, count, idPrefix = 'mqRetry' }: MqStationRetryProps) {
  const pedestal = isoPedestalPaths(60, 72, 48, 14)
  const alert = count > 0

  return (
    <div className={`mq-factory-station-graphic mq-factory-station-retry${alert ? ' mq-factory-station-retry--alert' : ''}`}>
      <svg className="mq-factory-station-graphic__svg" viewBox="0 0 120 108" aria-hidden>
        <ellipse cx="60" cy="82" rx="26" ry="5" className="mq-factory-station-graphic__shadow" />
        <g className="mq-factory-station-graphic__pedestal">
          <path d={pedestal.top} className="mq-factory-station-graphic__pedestal-top" />
          <path d={pedestal.left} className="mq-factory-station-graphic__pedestal-left" />
          <path d={pedestal.right} className="mq-factory-station-graphic__pedestal-right" />
        </g>
        <MqGlassCube idPrefix={`${idPrefix}-cube`} cx={60} cy={50} size={18} glow={alert}>
          <path
            d="M72 46 A12 12 0 1 1 68 58"
            className="mq-factory-station-retry__arrow"
            fill="none"
            strokeWidth="2.8"
            strokeLinecap="round"
          />
          <polygon points="72,42 78,46 72,50" className="mq-factory-station-retry__arrow-head" />
        </MqGlassCube>
        <MqStationCounter value={count} icon="retry" alert={alert} />
      </svg>
      <span className="mq-factory-station-graphic__label">{label}</span>
    </div>
  )
}
