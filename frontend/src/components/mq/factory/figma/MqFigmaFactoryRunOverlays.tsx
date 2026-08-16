import type { WorkshopKey } from '../mqFactoryMetrics'
import { FIGMA_CONVEYOR, figmaIsoPackage } from './mqFigmaConcretePaths'

const BELT_SLOT_X = [146, 188, 230, 272, 548, 590, 632, 674, 716, 758, 800, 842] as const
const LIVE_PACKAGE_X = [170, 430] as const

type MqFigmaFactoryRunOverlaysProps = {
  clipId: string
  workshopKey: WorkshopKey
}

/** 运行态传送带动画（与加工台机械臂分离，见 MqFigmaArmUnitLive）。 */
export default function MqFigmaFactoryRunOverlays({ clipId, workshopKey }: MqFigmaFactoryRunOverlaysProps) {
  const beltFill =
    workshopKey === 'index' ? '#72c98d' : workshopKey === 'post' ? '#7bdff4' : '#7fb9f4'

  return (
    <g className="mq-figma-run-overlay mq-figma-run-overlay--belt" pointerEvents="none" aria-hidden>
      <defs>
        <clipPath id={clipId}>
          <rect x="122" y="103" width="832" height="40" rx="2" />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clipId})`}>
        <g className="mq-figma-belt-slots-live">
          {BELT_SLOT_X.map((x) => (
            <rect key={x} x={x} y={FIGMA_CONVEYOR.slotY} width="18" height="8" rx="2" fill={beltFill} />
          ))}
          {BELT_SLOT_X.map((x) => (
            <rect
              key={`${x}-b`}
              x={x + 448}
              y={FIGMA_CONVEYOR.slotY}
              width="18"
              height="8"
              rx="2"
              fill={beltFill}
              opacity="0.9"
            />
          ))}
        </g>
        {LIVE_PACKAGE_X.map((x, index) => {
          const box = figmaIsoPackage(x, 106, 14)
          return (
            <g key={x} className={`mq-figma-live-package mq-figma-live-package--${index + 1}`}>
              <path d={box.left} className="mq-figma-package-face--left" />
              <path d={box.right} className="mq-figma-package-face--right" />
              <path d={box.top} className="mq-figma-package-face--top" />
            </g>
          )
        })}
      </g>
    </g>
  )
}
