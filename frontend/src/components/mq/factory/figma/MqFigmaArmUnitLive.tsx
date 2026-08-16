import { FIGMA_ARM_UNIT } from './mqFigmaArmLayout'
import { FigmaArmWorkbenchBase, FigmaWorkshopEngineer } from './mqFigmaConcreteParts'

/**
 * 运行态加工台：完整机械臂叠在 <use> 之上，动画仅作用于 pivot（前臂 + 焊枪）。
 */
export default function MqFigmaArmUnitLive() {
  const { x, y, pivotX, pivotY, tipX, tipY } = FIGMA_ARM_UNIT
  const linkDx = tipX - pivotX
  const linkDy = tipY - pivotY

  return (
    <g className="mq-figma-arm-unit-live" transform={`translate(${x} ${y})`} pointerEvents="none" aria-hidden>
      <FigmaArmWorkbenchBase />
      <g transform={`translate(${pivotX} ${pivotY})`}>
        <g className="mq-figma-arm-pivot-live">
          <animateTransform
            attributeName="transform"
            attributeType="XML"
            type="rotate"
            values="-10 0 0; 12 0 0; -10 0 0"
            keyTimes="0; 0.5; 1"
            dur="1.35s"
            repeatCount="indefinite"
            calcMode="spline"
            keySplines="0.42 0 0.58 1; 0.42 0 0.58 1"
          />
          <path
            d={`M0 0 L${linkDx} ${linkDy}`}
            strokeWidth="9"
            strokeLinecap="round"
            className="mq-figma-arm-link-live"
            fill="none"
          />
          <path d={`M${linkDx - 4} ${linkDy - 4} L${linkDx + 8} ${linkDy - 2} L${linkDx + 4} ${linkDy + 6} L${linkDx - 6} ${linkDy + 2} Z`} className="mq-figma-arm-nozzle-live" />
          <circle cx={linkDx} cy={linkDy} r="10" className="mq-figma-arm-joint mq-figma-arm-tip-live" />
          <circle cx={linkDx} cy={linkDy} r="5" className="mq-figma-arm-spark-live" />
        </g>
      </g>
      <FigmaWorkshopEngineer />
    </g>
  )
}
