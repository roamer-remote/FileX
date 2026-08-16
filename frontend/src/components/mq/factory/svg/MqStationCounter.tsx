type MqStationCounterProps = {
  value: number | string
  icon?: 'arrow' | 'gear' | 'recycle' | 'retry'
  alert?: boolean
  x?: number
  y?: number
}

export default function MqStationCounter({
  value,
  icon = 'arrow',
  alert = false,
  x = 42,
  y = 92,
}: MqStationCounterProps) {
  return (
    <g
      className={`mq-station-counter${alert ? ' mq-station-counter--alert' : ''}`}
      transform={`translate(${x}, ${y})`}
    >
      <rect x="0" y="0" width="36" height="14" rx="4" className="mq-station-counter__bg" />
      {icon === 'arrow' ? (
        <>
          <text x="7" y="10" className="mq-station-counter__sym">
            ↑
          </text>
          <text x="18" y="10.5" className="mq-station-counter__value">
            {value}
          </text>
          <text x="27" y="10" className="mq-station-counter__sym">
            ↓
          </text>
        </>
      ) : icon === 'gear' ? (
        <>
          <circle cx="9" cy="7" r="3.5" className="mq-station-counter__gear" fill="none" strokeWidth="1.2" />
          <text x="18" y="10.5" className="mq-station-counter__value">
            {value}
          </text>
        </>
      ) : icon === 'retry' ? (
        <>
          <text x="7" y="10" className="mq-station-counter__sym">
            ↻
          </text>
          <text x="18" y="10.5" className="mq-station-counter__value">
            {value}
          </text>
        </>
      ) : (
        <>
          <text x="7" y="10" className="mq-station-counter__sym">
            ♻
          </text>
          <text x="18" y="10.5" className="mq-station-counter__value">
            {value}
          </text>
        </>
      )}
    </g>
  )
}
