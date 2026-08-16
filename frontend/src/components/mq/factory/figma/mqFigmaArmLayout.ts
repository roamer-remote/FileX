import { FIGMA_STATION_LAYOUT, FIGMA_QUEUE_PREVIEW } from './mqFigmaTheme'

export { FIGMA_QUEUE_PREVIEW }

/** 加工台机械臂在 factory 符号内的位置（与 MqFigmaSvgDefs armUnit 一致） */
export const FIGMA_ARM_UNIT = {
  x: FIGMA_STATION_LAYOUT.process.x,
  y: FIGMA_STATION_LAYOUT.process.y,
  width: 170,
  height: 144,
  /** 上关节圆心 cx=115 cy=39 */
  pivotX: 115,
  pivotY: 39,
  tipX: 164,
  tipY: 76,
} as const

/** 运行态任务气泡：锚定在焊枪尖端上方，factory 组内坐标 */
export const FIGMA_TASK_BUBBLE = {
  width: 252,
  height: 108,
  /** 锚点 → 气泡底边的间距（含 callout 尾巴高度） */
  tailGap: 10,
  /** 下移气泡，避免多行任务信息贴住车间行顶部并遮挡用户名 */
  dropY: 24,
  anchorX: FIGMA_ARM_UNIT.x + FIGMA_ARM_UNIT.tipX,
  anchorY: FIGMA_ARM_UNIT.y + FIGMA_ARM_UNIT.tipY + 32,
} as const

/** 主队列工位下方排队 preview panel（factory 组内坐标） — SSOT: mqFigmaTheme.FIGMA_QUEUE_PREVIEW */
/** 相对锚点（焊枪尖端）的 foreignObject 矩形 */
export function figmaTaskBubbleForeignObject() {
  const { width, height, tailGap, dropY } = FIGMA_TASK_BUBBLE
  return {
    x: -width / 2,
    y: -(height + tailGap) + dropY,
    width,
    height,
  }
}
