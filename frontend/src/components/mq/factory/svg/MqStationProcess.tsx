import type { ReactNode } from 'react'
import MqStationCounter from './MqStationCounter'
import { isoPedestalPaths } from './mqIsometry'

type MqStationProcessProps = {
  label: string
  active?: boolean
  bubble?: ReactNode
  idPrefix?: string
  processCount?: number
}

export default function MqStationProcess({
  label,
  active = false,
  bubble,
  idPrefix = 'mqProcess',
  processCount = 0,
}: MqStationProcessProps) {
  const pedestal = isoPedestalPaths(60, 72, 48, 14)
  const count = active ? Math.max(processCount, 1) : processCount

  return (
    <div className={`mq-factory-station-graphic mq-factory-station-process${active ? ' mq-factory-station-process--active' : ''}`}>
      {bubble ? <div className="mq-factory-station-process__bubble-wrap">{bubble}</div> : null}
      <svg className="mq-factory-station-graphic__svg" viewBox="0 0 120 108" aria-hidden>
        <ellipse cx="60" cy="82" rx="26" ry="5" className="mq-factory-station-graphic__shadow" />
        <g className="mq-factory-station-graphic__pedestal">
          <path d={pedestal.top} className="mq-factory-station-graphic__pedestal-top" />
          <path d={pedestal.left} className="mq-factory-station-graphic__pedestal-left" />
          <path d={pedestal.right} className="mq-factory-station-graphic__pedestal-right" />
        </g>
        {/* 加工台底座 */}
        <path d="M38 58 L82 58 L78 68 L42 68 Z" className="mq-factory-station-process__table" />
        <path d="M38 58 L42 68 L42 72 L38 62 Z" className="mq-factory-station-process__table-side" />
        {/* 机械臂柱 */}
        <rect x="54" y="42" width="12" height="18" rx="3" className="mq-factory-station-process__column" />
        {/* 大臂 */}
        <path
          d="M60 42 L60 28 L78 22 L82 28 L66 32 Z"
          className={`mq-factory-station-process__arm${active ? ' mq-factory-station-process__arm--active' : ''}`}
        />
        {/* 小臂 */}
        <path
          d="M78 22 L92 18 L94 24 L82 28 Z"
          className={`mq-factory-station-process__forearm${active ? ' mq-factory-station-process__forearm--active' : ''}`}
        />
        {/* 焊枪头 */}
        <circle cx="94" cy="20" r="4" className="mq-factory-station-process__tip" />
        {active ? (
          <g className="mq-factory-station-process__sparks">
            <circle cx="98" cy="14" r="2.2" className="mq-factory-station__spark" />
            <circle cx="102" cy="18" r="1.6" className="mq-factory-station__spark mq-factory-station__spark--delay" />
            <circle cx="100" cy="10" r="1.4" className="mq-factory-station__spark mq-factory-station__spark--delay2" />
            <path d="M96 8 L104 16 M104 8 L96 16" className="mq-factory-station-process__weld-flash" strokeWidth="1.5" />
          </g>
        ) : null}
        <MqStationCounter value={count} icon="gear" />
      </svg>
      <span className="mq-factory-station-graphic__label">{label}</span>
    </div>
  )
}
